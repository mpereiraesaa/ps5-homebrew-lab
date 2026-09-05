.PHONY: all clean verify deploy-plan

all:
	bash build.sh

verify:
	python3 verify.py

deploy-plan:
	python3 deploy.py

clean:
	rm -rf build dist
