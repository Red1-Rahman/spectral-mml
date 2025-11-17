#!/usr/bin/env python3
"""
mml_player.py

Windows command-line Music Macro Language (MML) player with:
 - multi-channel support (channels separated by '|')
 - standard MML commands: t (tempo), o (octave), l (default length), v (volume),
   >/< octave shift, dotted notes '.', ties '&', rests 'r', numeric notes 'n'
 - tone color defined by Fourier coefficients vectors (real & imag per harmonic)
 - produces a temporary WAV and plays via winsound (Windows)

Usage examples:
  python mml_player.py "t120 o5 l4 v12 cdefgab>c"             # single channel
  python mml_player.py "t140 o5 l8 v10 c8e8g8c6|o4 g4b4d5"    # 2 channels separated by '|'
  python mml_player.py --timbre "1,0.5;0,0|1;0" "t120 o5 l4 cdefg" 
    # --timbre format per-channel: "real1,real2,...;imag1,imag2,..." each channel separated by '|'
"""

import argparse
import tempfile
import wave
import winsound
import numpy as np
import os
import sys
from math import sin, cos, pi

# Constants
A4_FREQ = 440.0
NOTE_TO_SEMITONE = {'c': -9, 'd': -7, 'e': -5, 'f': -4, 'g': -2, 'a': 0, 'b': 2}
SAMPLE_RATE = 44100
DEFAULT_TEMPO = 120
DEFAULT_OCTAVE = 4
DEFAULT_LENGTH = 4   # l4 -> quarter note
MAX_AMPLITUDE = 32767

def parse_args():
    p = argparse.ArgumentParser(description="Play MML (Music Macro Language) on Windows (multi-channel + Fourier timbres)")
    p.add_argument('mml', help='MML string. Multiple channels separated by | (pipe). Example: "t120 o5 l4 cdef|g,rest"')
    p.add_argument('--samplerate', '-r', type=int, default=SAMPLE_RATE, help='Sample rate (default 44100)')
    p.add_argument('--timbre', '-T', default=None,
                   help=("Timbre specification. Per-channel timbre separated by '|'. "
                         "Each timbre is: real1,real2,...;imag1,imag2,... "
                         "Example: --timbre \"1,0.5;0,0|1;0\""))
    p.add_argument('--tempo', '-t', type=int, default=None, help='Override tempo (BPM)')
    p.add_argument('--outfile', '-o', default=None, help='If set, save WAV to this file (otherwise plays and deletes temp file)')
    return p.parse_args()

# ---------- MML Parsing and representation ----------
class MMLNote:
    def __init__(self, freq, duration, volume=1.0):
        self.freq = freq      # None for rest
        self.duration = duration
        self.volume = volume

def frequency_from_note(letter=None, accidental=0, octave=4, n_number=None):
    # If numeric note provided (n# style), map 0- semitone from C0? We'll implement n as MIDI-like (n=0 -> C0?).
    if n_number is not None:
        # Map n to semitone number where n=0 is C0 (MML n convention varies; this is a sensible default)
        semitone = n_number
        freq = 16.351597831287414 * (2 ** (semitone / 12.0))  # C0 frequency approx 16.3516
        return freq
    if letter is None:
        return None
    base = NOTE_TO_SEMITONE[letter.lower()]
    semitone = base + accidental + (octave - 4) * 12
    freq = A4_FREQ * (2 ** (semitone / 12.0))
    return freq

def parse_mml_channel(mml_str, tempo_override=None):
    """
    Parse a single channel MML string and return a list of MMLNote objects.
    Supports:
      tNN tempo, oN octave, lN default length, vN volume (0-15-ish), > < octave shift,
      notes a-g with optional '+' or '#' or '-' accidental, nNN numeric note,
      r rest, . dotted, & tie (connect duration), numbers for length after note and / for length fraction
    """
    idx = 0
    length = len(mml_str)
    tempo = DEFAULT_TEMPO if tempo_override is None else tempo_override
    octave = DEFAULT_OCTAVE
    default_length = DEFAULT_LENGTH
    default_volume = 1.0
    notes = []
    tie_next = False

    def read_number():
        nonlocal idx
        start = idx
        while idx < length and mml_str[idx].isdigit():
            idx += 1
        if start == idx:
            return None
        return int(mml_str[start:idx])

    while idx < length:
        ch = mml_str[idx].lower()
        idx += 1

        if ch.isspace() or ch == ',':
            continue
        if ch == 't':            # tempo
            num = read_number()
            if num is not None:
                tempo = num
        elif ch == 'o':          # octave
            num = read_number()
            if num is not None:
                octave = num
        elif ch == 'l':          # default length
            num = read_number()
            if num is not None:
                default_length = num
        elif ch == 'v':          # volume 0-15 typical; map to 0.0-1.0
            num = read_number()
            if num is not None:
                default_volume = max(0.0, min(1.0, num / 15.0))
        elif ch == '>':
            octave += 1
        elif ch == '<':
            octave -= 1
        elif ch == 'r':          # rest
            # optional length after r
            num = read_number()
            length_spec = num if num is not None else default_length
            dur = length_to_seconds(length_spec, tempo)
            # dotted?
            if idx < length and mml_str[idx] == '.':
                idx += 1
                dur *= 1.5
            notes.append(MMLNote(None, dur, 0.0))
            tie_next = False
        elif ch == 'n':          # numeric note (n followed by number)
            num = read_number()
            if num is None:
                continue
            dur_spec = None
            if idx < length and mml_str[idx].isdigit():
                dur_spec = read_number()
            length_spec = dur_spec if dur_spec is not None else default_length
            dur = length_to_seconds(length_spec, tempo)
            if idx < length and mml_str[idx] == '.':
                idx += 1
                dur *= 1.5
            freq = frequency_from_note(n_number=num)
            if tie_next and notes and notes[-1].freq == freq:
                notes[-1].duration += dur
            else:
                notes.append(MMLNote(freq, dur, default_volume))
            tie_next = False
        elif ch in 'abcdefg':    # note letters
            accidental = 0
            # optionally followed by +/#/- for sharp/flat
            if idx < length and mml_str[idx] in ('+', '#'):
                accidental += 1
                idx += 1
            elif idx < length and mml_str[idx] == '-':
                accidental -= 1
                idx += 1
            # optional length number
            num = read_number()
            length_spec = num if num is not None else default_length
            dur = length_to_seconds(length_spec, tempo)
            # dotted note
            if idx < length and mml_str[idx] == '.':
                idx += 1
                dur *= 1.5
            # tie
            if idx < length and mml_str[idx] == '&':
                idx += 1
                tie_next = True
            freq = frequency_from_note(letter=ch, accidental=accidental, octave=octave)
            if tie_next and notes and notes[-1].freq == freq:
                notes[-1].duration += dur
                tie_next = False
            else:
                notes.append(MMLNote(freq, dur, default_volume))
            # reset tie if we used it
            if tie_next:
                tie_next = False
        else:
            # unknown char: skip
            continue

    return notes, tempo

def length_to_seconds(length_spec, tempo):
    # length_spec is like 4 for quarter note. Beat length in seconds:
    # quarter note length = 60 / tempo
    # so note length = (4 / length_spec) * (60 / tempo)
    return (4.0 / length_spec) * (60.0 / tempo)

# ---------- Timbre (Fourier) ----------
def parse_timbre_string(tstr):
    """
    Parse a timbre string like "r1,r2,r3; i1,i2,i3" (real;imag) or only reals "r1,r2,r3"
    Return tuple (real_list, imag_list) as numpy arrays (starting at harmonic 1).
    """
    if tstr is None or tstr.strip() == '':
        return None, None
    parts = tstr.split(';')
    reals = []
    imags = []
    if parts[0].strip():
        reals = [float(x) for x in parts[0].split(',') if x.strip()!='']
    if len(parts) > 1 and parts[1].strip():
        imags = [float(x) for x in parts[1].split(',') if x.strip()!='']
    # pad to same length
    L = max(len(reals), len(imags))
    if L == 0:
        return None, None
    reals += [0.0] * (L - len(reals))
    imags += [0.0] * (L - len(imags))
    return np.array(reals, dtype=float), np.array(imags, dtype=float)

def synth_note_wave(freq, duration, samplerate, real_coeffs=None, imag_coeffs=None, volume=1.0):
    """
    Synthesize a single tone using harmonic series defined by real,imag Fourier coefficients.
    real_coeffs[0] corresponds to harmonic k=1 (fundamental multiplier).
    If coeffs are None, default to simple saw-like partials (1/k amplitude).
    """
    if freq is None:
        return np.zeros(int(np.round(duration * samplerate)), dtype=np.float32)
    t = np.linspace(0, duration, int(np.round(duration * samplerate)), endpoint=False)
    if len(t) == 0:
        return np.zeros(0, dtype=np.float32)

    if real_coeffs is None and imag_coeffs is None:
        # default harmonic amplitudes: simple saw-ish odd+even partials
        # let's do first 10 harmonics with 1/k amplitude
        kmax = 12
        real_coeffs = np.array([1.0/k for k in range(1, kmax+1)], dtype=float)
        imag_coeffs = np.zeros_like(real_coeffs)
    else:
        if real_coeffs is None:
            real_coeffs = np.zeros_like(imag_coeffs)
        if imag_coeffs is None:
            imag_coeffs = np.zeros_like(real_coeffs)

    kmax = len(real_coeffs)
    wave = np.zeros_like(t, dtype=np.float64)
    for k in range(1, kmax+1):
        rk = real_coeffs[k-1]
        ik = imag_coeffs[k-1]
        # contribution = rk * cos(2π k f t) - ik * sin(2π k f t)
        phase_arg = 2.0 * pi * k * freq * t
        wave += rk * np.cos(phase_arg) - ik * np.sin(phase_arg)

    # normalize to peak 1 then scale by volume
    if np.max(np.abs(wave)) > 0:
        wave = wave / np.max(np.abs(wave))
    # apply quick linear attack+release envelope to avoid clicks
    n = len(wave)
    env = np.ones(n, dtype=np.float64)
    attack_len = min(int(0.005 * samplerate), n//10)  # up to 5 ms or 1/10th of note
    release_len = min(int(0.01 * samplerate), n//10)  # up to 10 ms or 1/10th
    if attack_len > 0:
        env[:attack_len] = np.linspace(0.0, 1.0, attack_len)
    if release_len > 0:
        env[-release_len:] = np.linspace(1.0, 0.0, release_len)
    wave = wave * env
    wave = wave * volume
    return wave.astype(np.float32)

# ---------- Rendering channels and mixing ----------
def render_channel(notes, samplerate, timbre_real=None, timbre_imag=None):
    parts = []
    for n in notes:
        w = synth_note_wave(n.freq, n.duration, samplerate, timbre_real, timbre_imag, volume=n.volume)
        parts.append(w)
    if len(parts) == 0:
        return np.array([], dtype=np.float32)
    return np.concatenate(parts)

def mix_channels(channel_waves):
    # pad to same length
    maxlen = max((len(w) for w in channel_waves), default=0)
    if maxlen == 0:
        return np.array([], dtype=np.float32)
    mix = np.zeros(maxlen, dtype=np.float64)
    for w in channel_waves:
        if len(w) == 0:
            continue
        mix[:len(w)] += w
    # simple normalization (prevent clipping)
    peak = np.max(np.abs(mix)) if maxlen>0 else 1.0
    if peak > 0:
        mix = mix / peak
    return (mix * 0.95).astype(np.float32)  # leave small headroom

# ---------- WAV write & play ----------
def write_wav(path, samples, samplerate):
    # samples float32 in -1..1
    # convert to int16
    int_samples = np.int16(np.clip(samples * MAX_AMPLITUDE, -MAX_AMPLITUDE, MAX_AMPLITUDE-1))
    with wave.open(path, 'wb') as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(samplerate)
        wf.writeframes(int_samples.tobytes())

def play_wav_windows(path, async_play=False):
    flags = winsound.SND_FILENAME
    if async_play:
        flags |= winsound.SND_ASYNC
    winsound.PlaySound(path, flags)

# ---------- Utility ----------
def parse_multi_channel_mml(mml_full):
    """
    Split by '|' into channels. Trim whitespace.
    """
    return [ch.strip() for ch in mml_full.split('|') if ch.strip()!='']

def parse_timbre_per_channel(timbre_arg, num_channels):
    """
    timbre_arg format: per-channel timbre separated by '|'
      each timbre: real1,real2,...;imag1,imag2,...
    return list of (real_array, imag_array) per channel (None if unspecified)
    """
    if timbre_arg is None:
        return [ (None, None) ] * num_channels
    parts = [p.strip() for p in timbre_arg.split('|')]
    result = []
    for i in range(num_channels):
        if i < len(parts) and parts[i] != '':
            r,i_ = parse_timbre_string(parts[i])
            result.append((r,i_))
        else:
            result.append((None,None))
    return result

# ---------- Main ----------
def main():
    args = parse_args()
    samplerate = args.samplerate
    mml = args.mml
    chan_strs = parse_multi_channel_mml(mml)
    num_channels = len(chan_strs)
    timbres = parse_timbre_per_channel(args.timbre, num_channels)

    channel_waves = []
    # parse and render each channel
    for i, ch in enumerate(chan_strs):
        notes, tempo = parse_mml_channel(ch, tempo_override=args.tempo)
        real_coeffs, imag_coeffs = timbres[i]
        # If provided coeff arrays shorter than 1 element, interpret None
        if real_coeffs is not None and len(real_coeffs) == 0:
            real_coeffs = None
        if imag_coeffs is not None and len(imag_coeffs) == 0:
            imag_coeffs = None
        wave_i = render_channel(notes, samplerate, real_coeffs, imag_coeffs)
        channel_waves.append(wave_i)

    mix = mix_channels(channel_waves)
    if len(mix) == 0:
        print("No audio generated (empty MML).")
        return

    # write wav to tempfile or outfile
    if args.outfile:
        outpath = args.outfile
        write_wav(outpath, mix, samplerate)
        print(f"WAV saved to {outpath}")
        print("Playing...")
        play_wav_windows(outpath)
    else:
        fd, path = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        try:
            write_wav(path, mix, samplerate)
            print("Playing...")
            play_wav_windows(path)
            # wait until done (synchronous) - winsound.PlaySound without SND_ASYNC will block
        finally:
            # remove file after playing
            try:
                os.remove(path)
            except Exception:
                pass

if __name__ == '__main__':
    main()
