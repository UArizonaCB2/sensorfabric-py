from setuptools import setup, find_packages

setup(
    name='sensorfabric',
    version='0.1.1',
    description='Python library for UA Sensor Fabric',
    license='MIT',
    url='https://github.com/UArizonaCB2/sensorfabric-py.git',
    author="Shravan Aras",
    author_email='shravanaras@arizona.edu',
    packages=['sensorfabric'],
    keywords='sensors sensorfabric',
    python_requires='>=3',
    install_requires=[
          'boto3',
          'pandas'
      ],
)
