PY  ?= python3
CXX ?= g++

.PHONY: help install verify demo mc sweep params test vectors test-firmware housing docs all clean

help:
	@echo "make install        - pasang dependensi Python"
	@echo "make verify         - uji verifikasi simulator (jalankan PERTAMA)"
	@echo "make demo           - satu run + grafik rinci      -> results/fig_trace.png"
	@echo "make mc             - Monte Carlo semua skenario   -> results/"
	@echo "make sweep          - sapuan ukuran respons biometrik -> results/"
	@echo "make housing        - bandingkan rumah terbuka vs tertutup"
	@echo "make test           - pytest (Python)"
	@echo "make test-firmware  - uji logika firmware C++ terhadap simulator Python"
	@echo "make docs           - ekspor tabel asumsi ke docs/asumsi.md"

install:
	$(PY) -m pip install -r requirements-dev.txt

verify:
	$(PY) sim/simulator.py verify

demo:
	$(PY) sim/simulator.py demo

mc:
	$(PY) sim/simulator.py mc --n 300 --seed 1

sweep:
	$(PY) sim/simulator.py sweep --n 150 --seed 2 --group rentan

params:
	$(PY) sim/simulator.py params

housing:
	$(PY) tools/compare_housing.py

test:
	$(PY) -m pytest -q

vectors:
	$(PY) tools/gen_vectors.py

test-firmware: vectors
	$(CXX) -std=c++17 -O2 -Wall -Wextra -Ifirmware/include firmware/host_test/host_test.cpp -o firmware/host_test/host_test
	./firmware/host_test/host_test firmware/host_test/vectors

docs:
	$(PY) tools/export_params_md.py

all: verify test test-firmware

clean:
	rm -rf firmware/host_test/vectors firmware/host_test/host_test .pytest_cache
