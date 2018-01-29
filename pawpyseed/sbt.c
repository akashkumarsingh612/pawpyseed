#include <stdio.h>
#include <stdlib.h>
#include <complex.h>
#include <math.h>
#include <omp.h>
#include <time.h>
#include <mkl.h>
#include <mkl_types.h>
#include "utils.h"
#include "sbt.h"

#define c 0.262465831
#define PI 3.14159265359

double complex* spherical_bessel_transform(double* r, double* f, double maxE, int N, int l, int m) {
	MKL_Complex16* x = mkl_malloc(N*sizeof(MKL_Complex16), 64);

	DFTI_DESCRIPTOR_HANDLE handle = 0;
	MKL_LONG dim = 1;
	MKL_LONG length = N;
	MKL_LONG status = 0;

	double complex* vals = malloc(N * sizeof(double complex));

	status = DftiCreateDescriptor(&handle, DFTI_DOUBLE, DFTI_COMPLEX, dim, length);
	status = DftiCommitDescriptor(handle);
	status = DftiComputeBackward(handle, x);

	double drho = log(r[1] / r[0]);
	double rhomin = log(r[0]);
	double rmin = r[0];
	double kmin = pow(maxE * c, 0.5) * exp(-N * drho);
	double kappamin = log(kmin);
	double t[N];
	double dt = 2 * PI / N / drho;
	double phase = 0;
	for (int i = 0; i < N; i++) {
		t[i] = dt * i;
	}
	for (int m = 0; m < N; m++) {
		x[m].real = pow(r[m], 1.5) * f[m];
		x[m].imag = 0;
	}
	double rp, ip;
	status = DftiComputeBackward(handle, x);
	for (int n = 0; n < N/2; n++) {
		rp = x[n].real * creal(M(l, t[n])) - x[n].imag * cimag(M(l, t[n]));
		ip = x[n].imag * creal(M(l, t[n])) + x[n].real * cimag(M(l, t[n]));
		phase = I * (kappamin + rhomin) * n * dt;
		M(l, t[n]);
		x[n].real = rp * cos(phase) - ip * sin(phase);
		x[n].imag = ip * cos(phase) + rp * sin(phase);
		if (n > N/2) {
			x[n].real = 0;
			x[n].imag = 0;
		}
	}
	status = DftiComputeBackward(handle, x);
	double kp = 0;
	for (int p = 0; p < N; p++) {
		kp = kmin * exp(p * drho);
		vals[p] = x[p].real + I * x[p].imag;
		vals[p] *= 2 / N / pow(kp, 1.5);
	}
	return vals;
}
