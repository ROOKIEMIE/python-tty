from setuptools import setup, find_packages

setup(
    name='file_manager',
    version='0.1',
    packages=find_packages(),
    description='This is a file manager demo to show how to use this tty framework',
    author='ROOKIEMIE',
    install_requires=[
        'prompt_toolkit>=3.0.32',
        'tqdm',
        'psutil'
    ]
)
