from setuptools import setup, find_packages
from pathlib import Path

ROOT = Path(__file__).parent
long_description = (ROOT / "README.md").read_text(encoding="utf-8")

setup(
    name="python-tty",
    version="0.1.2rc2",
    description="A multi-console TTY framework for complex CLI/TTY apps",
    long_description=long_description,
    long_description_content_type="text/markdown",
    author="ROOKIEMIE",
    url="https://github.com/ROOKIEMIE/python-tty",
    package_dir={"": "src"},
    packages=find_packages(where="src", exclude=("tests*", "demos*", "docs*")),
    include_package_data=True,
    python_requires=">=3.10",
    install_requires=[
        "prompt_toolkit>=3.0.32",
        "tqdm",
    ],
    license="Apache-2.0",
    classifiers=[
        "License :: OSI Approved :: Apache Software License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
    ],
)
