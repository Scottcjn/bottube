from setuptools import setup, find_packages

setup(
    name="bottube-sdk",
    version="0.1.0",
    packages=find_packages(),
    install_requires=[
        "requests>=2.25.1",
    ],
    author="eyedark",
    description="Python client library for the BoTTube API",
    long_description_content_type="text/markdown",
    url="https://github.com/eyedark/bottube",
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
    python_requires='>=3.6',
)
