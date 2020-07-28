#! /usr/bin/env python3 

import setuptools
import os
import re

PACKAGE = setuptools.find_packages(exclude=('tests',))[0]

def get_readme():
    with open("README.md", "r") as fh:
        text = fh.read()
    return text

def read_init(splitlines=False):
    here = os.path.abspath(os.path.dirname(__file__))
    filename = os.path.join(here, PACKAGE, '__init__.py')
    with open(filename) as fh:
        lines = fh.read()
    if splitlines:
        lines = lines.splitlines()
    return lines

def get_version():
    lines = read_init(splitlines=True)
    for line in lines:
        match = re.search('__version__\s*=\s*([\'"])(.*)\\1', line)
        if match:
            return match.groups()[1]
    raise RuntimeError("Unable to find version string.")

# Python package install
 
setuptools.setup(
    name='oifits',
    version=get_version(),
    packages=setuptools.find_packages(),
    license='LICENSE.txt',
    author="Régis Lachaume",
    author_email="regis.lachaume@gmail.com",
    description='Process astronomical data from European Southern Observatory',
    long_description=get_readme(),
    classifiers=[
        "Programming Language :: Python :: 3",
        "Development Status :: 1 - Planning ",
        "Operating System :: OS Independent",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Astronomy",
        "License :: Public Domain",
    ],
    python_requires='>=3.6',
    install_requires=[
        "astropy>=4.0", 
        "numpy>=2.0",
        "scipy",
    ],
)
