from setuptools import setup, find_packages

setup(
    name='python-tty',
    version='0.1',
    packages=find_packages(),
    description='This is a tty framework developed by Python, aiming to simplify complex tty development',
    author='ROOKIEMIE',
    url='https://github.com/ROOKIEMIE/python-tty',
    install_requires=[
        'prompt_toolkit>=3.0.32',
        'tqdm'
    ]
)
