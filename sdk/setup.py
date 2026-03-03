from setuptools import setup, find_packages

setup(
    name="bottube-sdk",
    version="1.0.0",
    description="Python SDK for BoTTube API",
    author="Atlas",
    packages=find_packages(),
    install_requires=[
        "requests>=2.28.0",
    ],
    python_requires=">=3.8",
)
