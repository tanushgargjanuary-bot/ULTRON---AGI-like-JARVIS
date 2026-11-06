/* native/frame.c — the shape of a hybrid: one hot loop in C, called from Python.
 *
 * Nothing in Ultron *needs* this today: the measured cost of classifying an
 * audio frame in Python is 39.5 microseconds against a 30,000 microsecond
 * budget. This file exists as the worked example of HOW to move a hot leaf into
 * a faster language without rewriting the shell — and as a measurement, because
 * "C is faster" is a claim, and claims in this project get measured.
 *
 * Build:  gcc -O2 -shared -fPIC native/frame.c -o native/libframe.so
 * Call:   ctypes.CDLL("native/libframe.so").frame_level
 */
#include <stdint.h>

typedef struct {
    int     peak;        /* highest absolute sample, 0..32768 */
    int     rms;         /* root mean square, rounded */
    int     crossings;   /* zero crossings, a cheap voicing hint */
} Level;

Level frame_level(const int16_t *samples, int count)
{
    Level out = {0, 0, 0};
    if (count <= 0) {
        return out;
    }
    long long sum_squares = 0;
    int previous = 0;
    for (int i = 0; i < count; i++) {
        int value = samples[i];
        int magnitude = value < 0 ? -value : value;
        if (magnitude > out.peak) {
            out.peak = magnitude;
        }
        sum_squares += (long long)value * value;
        if (i > 0 && ((value >= 0) != (previous >= 0))) {
            out.crossings++;
        }
        previous = value;
    }
    /* integer square root, so the answer needs no libm and no float drift */
    long long mean = sum_squares / count;
    long long root = 0;
    long long bit = 1LL << 30;
    while (bit > mean) {
        bit >>= 2;
    }
    while (bit) {
        if (mean >= root + bit) {
            mean -= root + bit;
            root = (root >> 1) + bit;
        } else {
            root >>= 1;
        }
        bit >>= 2;
    }
    out.rms = (int)root;
    return out;
}
