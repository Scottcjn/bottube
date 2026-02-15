from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as f:
    long_description = f.read()

setup(
    name="bottube-cli",
    version="0.1.0",
    author="AI Bounty Hunter",
    description="BoTTube CLI - Command-line interface for BoTTube",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/dunyuzoush-ch/bottube-cli",
    packages=find_packages(),
    python_requires=">=3.8",
    install_requires=["requests>=2.28.0"],
    extras_require={
        "dev": ["pytest>=7.0.0", "pytest-cov>=4.0.0"],
    },
    entry_points={
        'console_scripts': [
            'bottube=bottube.__main__:main',
        ],
    },
    classifiers=[
        "Development Status :: Alpha",
        "Intended Audience :: Developers",
        "License :: MIT",
        "Programming Language :: Python :: 3",
    ],
)
