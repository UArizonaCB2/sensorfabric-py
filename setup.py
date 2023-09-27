from setuptools import setup, find_packages

long_description = 'Python library for UA Sensor Fabric'

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name='sensorfabric',
    version='2.0.3',
    description='Python library for UA Sensor Fabric',
    long_description=long_description,
    long_description_content_type="text/markdown",
    license='MIT',
    url='https://github.com/UArizonaCB2/sensorfabric-py.git',
    author="Shravan Aras",
    author_email='shravanaras@arizona.edu',
    packages=['sensorfabric'],
    keywords='sensors sensorfabric',
    python_requires='>=3',
    install_requires=[
          'boto3==1.28.49',
          'pandas==2.1.0',
          'numpy==1.25.2',
          'pyjwt==2.8.0',
          'configparser==6.0.0',
          'pathlib==1.0.1',
          'cryptography==41.0.4',
          'requests==2.31.0',
      ],
)
