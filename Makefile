CXX ?= g++
CXXFLAGS ?= -O3 -std=c++17 -Wall -Wextra -Wpedantic -Werror
OPENMP ?= -fopenmp

.PHONY: all smoke confirm clean
all: hashjoin

hashjoin: src/main.cpp
	$(CXX) $(CXXFLAGS) $(OPENMP) $< -o $@

smoke: hashjoin
	bash scripts/run_smoke.sh

confirm:
	bash scripts/run_confirmation.sh

clean:
	rm -f hashjoin hashjoin.exe smoke_results.csv results.csv
