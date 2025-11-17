/*
Spectral-MML C Synthesizer with Fourier Timbres
Polyphonic MML player with WAV output
*/

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>

#define SAMPLE_RATE 44100
#define MAX_CHANNELS 4
#define MAX_HARMONICS 16
#define MAX_NOTES 128
#define MAX_TIMBRE_STR 256

typedef struct {
    double real[MAX_HARMONICS];
    double imag[MAX_HARMONICS];
    int num_harmonics;
} Timbre;

typedef struct {
    char note;      // 'c'-'g' or 'r'
    int octave;
    double duration; // in seconds
} Note;

typedef struct {
    Note notes[MAX_NOTES];
    int note_count;
    Timbre timbre;
} Channel;

// Convert note to frequency (C4=261.63 Hz)
double note_freq(char note, int octave) {
    switch(note) {
        case 'c': return 261.63 * pow(2, octave-4);
        case 'd': return 293.66 * pow(2, octave-4);
        case 'e': return 329.63 * pow(2, octave-4);
        case 'f': return 349.23 * pow(2, octave-4);
        case 'g': return 392.00 * pow(2, octave-4);
        case 'a': return 440.00 * pow(2, octave-4);
        case 'b': return 493.88 * pow(2, octave-4);
        default: return 0.0; // rest
    }
}

// Write WAV header
void write_wav_header(FILE *f, int total_samples) {
    int byte_rate = SAMPLE_RATE * 2; // mono 16-bit
    int data_size = total_samples * 2;

    fseek(f, 0, SEEK_SET);
    fwrite("RIFF", 1, 4, f);
    int chunk_size = 36 + data_size;
    fwrite(&chunk_size, 4, 1, f);
    fwrite("WAVE", 1, 4, f);

    fwrite("fmt ", 1, 4, f);
    int subchunk1 = 16;
    fwrite(&subchunk1, 4, 1, f);
    short audio_format = 1;
    fwrite(&audio_format, 2, 1, f);
    short num_channels = 1;
    fwrite(&num_channels, 2, 1, f);
    int sample_rate = SAMPLE_RATE;
    fwrite(&sample_rate, 4, 1, f);
    fwrite(&byte_rate, 4, 1, f);
    short block_align = 2;
    fwrite(&block_align, 2, 1, f);
    short bits_per_sample = 16;
    fwrite(&bits_per_sample, 2, 1, f);

    fwrite("data", 1, 4, f);
    fwrite(&data_size, 4, 1, f);
}

// Parse timbre from string: "1,0.5;0 | 1;0"
void parse_timbres(const char *str, Timbre *timbres, int *num_channels) {
    char buf[strlen(str)+1];
    strcpy(buf,str);
    char *tok = strtok(buf,"|");
    int ch=0;
    while(tok && ch<MAX_CHANNELS) {
        timbres[ch].num_harmonics = 0;
        char *part = strtok(tok,";");
        if(part) {
            // real components
            char *r_tok = strtok(part,",");
            while(r_tok && timbres[ch].num_harmonics < MAX_HARMONICS) {
                timbres[ch].real[timbres[ch].num_harmonics] = atof(r_tok);
                timbres[ch].imag[timbres[ch].num_harmonics] = 0.0; // default
                r_tok = strtok(NULL,",");
                timbres[ch].num_harmonics++;
            }
        }
        part = strtok(NULL,";");
        if(part) {
            // imag components
            int i=0;
            char *i_tok = strtok(part,",");
            while(i_tok && i < timbres[ch].num_harmonics) {
                timbres[ch].imag[i] = atof(i_tok);
                i_tok = strtok(NULL,",");
                i++;
            }
        }
        ch++;
        tok = strtok(NULL,"|");
    }
    *num_channels = ch;
}

// Simple MML parser
int parse_mml(const char *mml, Channel *channels, Timbre *timbres, int num_channels) {
    char *mml_copy = strdup(mml);
    char *tok = strtok(mml_copy,"|");
    int max_samples=0;

    for(int ch=0; ch<num_channels && tok; ch++, tok=strtok(NULL,"|")) {
        int note_idx=0;
        int octave=4;
        double note_length=0.5;
        for(int i=0; tok[i]; i++) {
            char c = tok[i];
            if(c >= 'a' && c <= 'g') {
                channels[ch].notes[note_idx].note = c;
                channels[ch].notes[note_idx].octave = octave;
                channels[ch].notes[note_idx].duration = note_length;
                note_idx++;
            } else if(c=='r') {
                channels[ch].notes[note_idx].note='r';
                channels[ch].notes[note_idx].octave=0;
                channels[ch].notes[note_idx].duration=note_length;
                note_idx++;
            } else if(c=='o') { i++; octave=tok[i]-'0'; }
            else if(c=='l') { i++; note_length=1.0/(tok[i]-'0'); }
        }
        channels[ch].note_count=note_idx;
        channels[ch].timbre = timbres[ch];

        double ttime=0.0;
        for(int n=0; n<note_idx; n++) ttime+=channels[ch].notes[n].duration;
        int samples = (int)(ttime*SAMPLE_RATE);
        if(samples>max_samples) max_samples=samples;
    }
    free(mml_copy);
    return max_samples;
}

// Synthesize a note into a buffer
void synthesize_note(double *buffer,int buf_len,int start_idx,Note n,Timbre t) {
    int total_samples = (int)(n.duration*SAMPLE_RATE);
    for(int i=0;i<total_samples && start_idx+i<buf_len;i++){
        double t_sec = (double)i/SAMPLE_RATE;
        double s=0.0;
        if(n.note!='r'){
            double f0=note_freq(n.note,n.octave);
            for(int h=0;h<t.num_harmonics;h++){
                s += t.real[h]*cos(2*M_PI*(h+1)*f0*t_sec)
                   - t.imag[h]*sin(2*M_PI*(h+1)*f0*t_sec);
            }
        }
        buffer[start_idx+i] += s;
    }
}

int main(int argc,char **argv){
    if(argc<2){ printf("Usage: %s \"MML_STRING\" [--timbre TIMBRE_STRING]\n",argv[0]); return 1; }

    Channel channels[MAX_CHANNELS]={0};
    Timbre timbres[MAX_CHANNELS]={0};
    int num_channels=2; // default

    // Default timbres
    timbres[0].num_harmonics=3; timbres[0].real[0]=1; timbres[0].real[1]=0.5; timbres[0].real[2]=0.25;
    timbres[1].num_harmonics=1; timbres[1].real[0]=1.0;

    // Check for --timbre argument
    for(int i=2;i<argc;i++){
        if(strcmp(argv[i],"--timbre")==0 && i+1<argc){
            parse_timbres(argv[i+1],timbres,&num_channels);
            break;
        }
    }

    int buffer_len = parse_mml(argv[1],channels,timbres,num_channels);
    double *buffer = calloc(buffer_len,sizeof(double));

    // Mix channels into buffer
    for(int ch=0;ch<num_channels;ch++){
        int start_idx=0;
        for(int n=0;n<channels[ch].note_count;n++){
            synthesize_note(buffer,buffer_len,start_idx,channels[ch].notes[n],channels[ch].timbre);
            start_idx += (int)(channels[ch].notes[n].duration*SAMPLE_RATE);
        }
    }

    // Normalize buffer to -1.0..1.0
    double max_amp=0.0;
    for(int i=0;i<buffer_len;i++){ if(fabs(buffer[i])>max_amp) max_amp=fabs(buffer[i]); }
    if(max_amp>1.0) for(int i=0;i<buffer_len;i++) buffer[i]/=max_amp;

    FILE *f=fopen("output.wav","wb");
    if(!f){ perror("Cannot open output"); return 1; }

    // placeholder header
    for(int i=0;i<44;i++) fputc(0,f);

    // write samples
    for(int i=0;i<buffer_len;i++){
        double s=buffer[i];
        if(s>1.0) s=1.0; if(s<-1.0) s=-1.0;
        short sample=(short)(s*32767);
        fwrite(&sample,sizeof(short),1,f);
    }

    write_wav_header(f,buffer_len);
    fclose(f);
    free(buffer);

    printf("WAV file written: output.wav\n");
    return 0;
}
