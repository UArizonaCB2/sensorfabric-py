from setuptools import setup, find_packages

setup(
    name='sensorfabric',
    version='0.1.1',
    description='Python library for UA Sensor Fabric',
    license='MIT',
    author="Shravan Aras",
    author_email='shravanaras@arizona.edu',
    packages=find_packages('src'),
    keywords='sensors sensorfabric',
    python_requires='>=3'
    install_requires=[
          'boto3',
          'pandas'
      ],
)
