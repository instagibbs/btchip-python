from btchip.btchip import *
from btchip.btchipUtils import *
from bitcoin.core import Hash160
import hashlib
from bitcoin.base58 import encode
import struct

keyPath = raw_input("Please enter keypath of desired xpub\n")[2:]

net = raw_input("(m)ainnet or (t)estnet?\n")
if net == "m":
    version = "0488B21E".decode('hex')
elif net == "t":
    version = "043587cf".decode('hex')

# Optional setup
dongle = getDongle(True)
app = btchip(dongle)

# Start signing
pubkey = app.getWalletPublicKey(keyPath)
if keyPath <> "":
    parentPath = ""
    for ind in keyPath.split("/")[:-1]:
        parentPath += ind+"/"
    parentPath = parentPath[:-1]

    parent = app.getWalletPublicKey(parentPath)
    fpr = Hash160(compress_public_key(parent["publicKey"]))[:4]
    childstr = keyPath.split("/")[-1]
    hard = 0
    if childstr[-1] == "'":
        childstr = childstr[:-1]
        hard = 0x80000000
    child = struct.pack(">I", int(childstr)+hard)
# Special case for m
else:
    child = "00000000".decode('hex')
    fpr = child

chainCode = pubkey["chainCode"]
publicKey = compress_public_key(pubkey["publicKey"])

depth = len(keyPath.split("/")) if len(keyPath) > 0 else 0
print(keyPath.split("/"))
depth = struct.pack("B", depth)

extkey = version+depth+fpr+child+chainCode+publicKey
checksum = hashlib.sha256(hashlib.sha256(extkey).digest()).digest()[:4]

print("Extended pubkey:\n" + encode(extkey+checksum))
