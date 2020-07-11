from setuptools import setup, find_packages

from codecs import open
from os import path

here = path.abspath(path.dirname(__file__))

with open(path.join(here, "README.md"), encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="panifex",
    version="1.0",
    description="A make-like DI-based Python build system.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/lainproliant/panifex",
    author="Lain Musgrove (lainproliant)",
    author_email="lain.proliant@gmail.com",
    license="MIT",
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Developers",
        "Topic :: Software Development :: Build Tools",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3.8",
    ],
    keywords="build make",
    packages=find_packages(),
    install_requires=["xeno>=4.1.0", "ansilog"],
    extras_require={},
    package_data={'panifex': []},
    data_files=[],
    entry_points={"console_scripts": ['bake=panifex.bake:main']},
)
