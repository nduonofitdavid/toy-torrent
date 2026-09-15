# Byte Strings
The number of bytes in the string are encoded in base 10. The content specified by the length are a sequence of bytes not a textual string.

An empty string is encoded as 0:

# Lists
lists begin with l and end with e. elements are bencoded values without delimiters. e.g 17:bencodedi-20ee corresponds to the string bencoded and the integer -20.

an empty dictionary is encoded as de

A dictionary contains key value pairs, keys are byte strings and must appear in lexicographical order. Each key is immediately followed by its value, which can be any bencoded type.

we can have a set containing action keys
we can have a stack containing action keys, and the index where that action key was found

d7:meaningi42e4:wiki7:bencodee

('l', 4)
(:, 7)

Then we know the length of the diction is int of [4:7]

strings
 
length:content
5:water

integers
i<number>e
i72e

lists
le
le on its own means an empty list
l<items>e means non empyt list

an action character directly followed by another alphabet cancels that action character
except that action character is another action character itself, then we add that action character to the stack and repeat the logic

when ever we get a number, we can check the top of the stack to see if we have a digit signifier there already

for dicts we need not worry about lists because lists are not hashable

lliae

ie != not valid combination
le = []
de = []

A torrent file, also knownas a metainfo file contains a bencoded dictionary with the following keys and values

announce: 
A url to a tracker, this tracker is a central server that keeps track of peers participating in the sharing of a torrent.

info:
A dictionary with keys:
length: size of the file in bytes, for single-file torrents
name: suggested name to save the file or directory as
piece length: number of bytes in each piece
pieces: concatenated SHA-1 hashes of each piece

A torrent fine is split into equally-sized parts called pieces. A piece is usually 256kb or 1mb in size.

Each piece has a hash value that allows us to verify the integrity of each piece we download. Piece length is the number of bytes in each piece, and pieces are concatenated sha-1 hashes of each piece (20 bytes each), a string

# Peers
when you make a request to the tracker url, it returns a list of peers currently sharing that file. The list of peers is implemented as a list of bencoded dicts. each dict contains a peer id, ip, and port.

peer id is 20 bytes plus 3 bytes bencoding overhead, and contains a domain name and an ip address, and an integer port number