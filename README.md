# Spectral-MML: A Polyphonic MML Synthesizer with User-Defined Fourier-Domain Timbres
Spectral-MML is a Windows command-line tool written in Python that parses BASIC-style Music Macro Language (MML) and synthesizes polyphonic audio using additive spectral synthesis. Each channel can use a custom timbre defined by vectors of real and imaginary Fourier components, enabling precise harmonic control and novel sound design.

## Features
- BASIC-style MML parsing
- Supports: t (tempo), o (octave), l (default length), v (volume), notes a–g, sharps/flats (#/+/-), numeric notes (n), rests (r), ties (&), dotted notes, < and > for octave shifts.
- Multi-channel support
- Use | to separate channels. Channels are mixed into a single audio output.
- Custom timbres via Fourier components
- Per-channel timbres are defined using real and imaginary harmonic coefficient vectors.
- Direct PCM synthesis
- Generates full audio using additive synthesis and outputs WAV files. Optional real-time playback on Windows.
- Lightweight and portable
- Single-file implementation (mml_player.py), minimal dependencies (numpy).

## Why Spectral-MML?
Classic MML engines rely on fixed waveforms, FM operators, or MIDI output. Spectral-MML extends the MML paradigm by allowing explicit spectral control, where each instrument can be defined as a vector of Fourier magnitudes and phases. This enables:
- Precise harmonic shaping
- Easy experimentation with timbre
- Educational demonstrations of Fourier synthesis
- A modern upgrade to retro-style music programming

## Installation
Requires Python 3.8+ and:
pip install numpy

Clone or download the repository and run mml_player.py:
git clone https://github.com/Red1-Rahman/spectral-mml.git
cd spectral-mml
python mml_player.py "your_mml_here"

## Usage Examples
### Single Channel
python mml_player.py "t120 o5 l4 cdefgab>c"

### Multi-Channel
python mml_player.py "t120 o5 l4 c4e4g4 | o4 g4b4d5"

### Custom Timbres
python mml_player.py \
  --timbre "1,0.5,0.25;0,0,0 | 1;0" \
  "t130 o5 l4 cdefg | o4 g4b4d5"

## Timbre Format (Fourier Coefficients)
Use the --timbre argument to define one timbre per channel, separated by |. Format:
real1,real2,real3,... ; imag1,imag2,imag3,...

- real_k → cosine amplitude for harmonic k
- imag_k → sine amplitude for harmonic k (phase control)
- Number of elements = number of harmonics
- Imaginary part (; imag...) is optional
- Missing values are treated as 0

### Examples
- Three-Harmonic Bright Tone: `1,0.5,0.25;0,0,0`
- Pure Sine Wave: `1`
- Two Channels with Different Timbres: `1,0.5,0.25;0,0,0 | 1;0`

## How it Works
Each note is synthesized as:
wave(t) = Σ_k [ real_k * cos(2π k f t) - imag_k * sin(2π k f t) ]

The vectors define the harmonic makeup and phase of your custom instrument.

## Project Links
- [mml_player.py](https://github.com/Red1-Rahman/spectral-mml/blob/main/mml_player.py)

## License
MIT License. See LICENSE for details.

## Contributing
Contributions, bug reports, and feature requests are welcome. Open an issue, submit a pull request, or join the - [Discussions](https://github.com/Red1-Rahman/spectral-mml/discussions) to share ideas and feedback.


## Citation
If you use Spectral-MML in research or projects, please cite: Spectral-MML: A Polyphonic MML Synthesizer with User-Defined Fourier-Domain Timbres.
