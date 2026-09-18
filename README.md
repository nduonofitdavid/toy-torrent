# Mini Torrent Client
This repository contains code from implementing a mini bittorrent client in python. The code was largely written by following the information available on the bittorrent website, and largely from auditing the [codecrafters bittorrent challenge](https://app.codecrafters.io/courses/bittorrent). 

This is by no means an efficient implementation of the protocol, or a standard bittorrent client, some assumptions are made such as a peer always having an index, amongst others. More information about the assumptions made can be found by auditing the [codecrafters bittorrent challenge](https://app.codecrafters.io/courses/bittorrent).

# Setup
The setup process is relatively straight forward, clone the github repository, and install the requirements using uv. More information can be found about installing uv on your environment if you don't have one [here](https://docs.astral.sh/uv/getting-started/installation/)

To install the requirements after cloning the repository and installing uv, use the uv sync command, this should work, provided you did not delete the uv.lock file.

``` bash
uv sync
```

After that, for more instructions on how to use, check out the tests directory, It provides shell files with instructions on how to interact with the program.

# Future Improvements
As mentioned above, this repository does not contain an efficient implementation of a bittorrent client in some aspects. Steps that could be taken to improve performance include, reusing sockets when downloading multiple pieces, using worker queues to retry failed piece downloads, amongst others.