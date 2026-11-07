import setuptools

with open("README.md", "r") as fh:
    long_description = fh.read()

setuptools.setup(
    name="pixelsort",
    version="1.0.2+fork.1",
    author="Bernard Zhao",
    author_email="bernardzhao@berkeley.edu",
    description="An image pixelsorter for Python.",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/spebby/pixelsort",
    project_urls={
        "Upstream": "https://github.com/satyarth/pixelsort",
    },
    packages=setuptools.find_packages(),
    install_requires=["Pillow"],
    classifiers=[
        "Programming Language :: Python",
        "License :: OSI Approved :: MIT License",
        "Operating System :: OS Independent",
    ],
)
