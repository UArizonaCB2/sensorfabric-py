from setuptools import setup, find_packages

long_description = 'Python library for UA Sensor Fabric'

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='sensorfabric',
    version='3.2.2',
    description='Python library for UA Sensor Fabric',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='MIT',
    url='https://github.com/UArizonaCB2/sensorfabric-py.git',
    author="Shravan Aras",
    author_email='shravanaras@arizona.edu',
    packages=find_packages(),
    keywords='sensors sensorfabric',
    python_requires='>=3',
    install_requires=[
          'boto3',
          'pandas',
          'numpy',
          'pyjwt==2.10.1',
          'jsonschema==4.24.0',
          'configparser',
          'pathlib',
          'cryptography',
          'requests',
      ],
)
