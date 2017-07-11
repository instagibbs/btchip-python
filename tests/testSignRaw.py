import sys
from btchip.btchip import *
from btchip.btchipUtils import *
from bitcoin.rpc import Proxy
import bitcoin
import sys

# This script will create a funded transaction from the wallet and sign
# This script requires you be running hdwatchonly(https://github.com/bitcoin/bitcoin/pull/9728)
# and set the "donglePath" variable below to whichever account xpubkey you
# imported into your Core wallet.
#
# Also make sure that any funds in your wallet are p2pkh;
# This means that any regtest `generate` should be replaced
# by `generatetoaddress` to avoid funding the txn with p2pk outputs.
#
# Other dependencies:
# python-bitcoinlib
# btchip-python
# and of course a connected Ledger Nano S
# running the bitcoin app

# Resources:
# https://ledgerhq.github.io/btchip-doc/bitcoin-technical-beta.html most up to date spec

if len(sys.argv) < 4:
    print("Please give hex of transaction to sign, xpub path, and network name")
    sys.exit(-1)

rawTxn = sys.argv[1]
donglePath = sys.argv[2][2:]
network = sys.argv[3]

# Setup dongle
dongle = getDongle(True)
app = btchip(dongle)
bitcoin.SelectParams(network)

try:
    bitcoin = Proxy()
except:
    print("Make sure bitcoind is running.")
    sys.exit(-1)

decodedTxn = bitcoin.call("decoderawtransaction", rawTxn)

# Get input transactions
rawInputs = []
inputTxids = []
inputVouts = []
inputAddrs = []
inputPaths = []
inputPubKey = []
inputSeq = []
inputType = []
redeemScripts = []
for input in decodedTxn["vin"]:
    walletInput = bitcoin.call("gettransaction", input["txid"])
    decodedInput = bitcoin.call("decoderawtransaction", walletInput["hex"])
    rawInputs.append(walletInput["hex"])
    inputTxids.append(input["txid"])
    inputVouts.append(input["vout"])
    inputAddrs.append(decodedInput["vout"][input["vout"]]["scriptPubKey"]["addresses"][0])
    inputType.append(decodedInput["vout"][input["vout"]]["scriptPubKey"]["type"])
    validata = bitcoin.validateaddress(inputAddrs[-1])
    if validata["isscript"] == True:
        if validata["script"] != "multisig":
            raise Exception("Only multisig p2sh are currently supported")
        subpaths = []
        if "addresses" in validata:
            for address in validata["addresses"]:
                subvalid = bitcoin.validateaddress(address)
                if "hdkeypath" in subvalid:
                    subpaths.append(subvalid["hdkeypath"][1:])
        inputPaths.append(subpaths)
        inputPubKey.append("")
        redeemScripts.append(validata["hex"])

    elif "hdkeypath" not in validata:
        raise Exception("Can not find keypath from address. Not ours?")
    else:
        inputPaths.append([validata["hdkeypath"][1:]])
        inputPubKey.append(validata["pubkey"])
        redeemScripts.append("")

    seq = format(input["sequence"], 'x')
    seq = seq.zfill(len(seq)+len(seq)%2)
    inputSeq.append(seq)

spendTxn = bytearray(rawTxn.decode('hex'))

prevoutScriptPubkey = []
outputData = ""
trustedInputs = []
signatures = []
# Compile trusted inputs for later signing
for i in range(len(inputTxids)):
    inputTransaction = bitcoinTransaction(bytearray(rawInputs[i].decode('hex')))
    trustedInputs.append(app.getTrustedInput(inputTransaction, inputVouts[i]))
    trustedInputs[-1]["sequence"] = inputSeq[i]
    prevoutScriptPubkey.append(inputTransaction.outputs[inputVouts[i]].script)

newTx = True
# Now we sign the transaction, input by input
for i in range(len(inputTxids)):
    signature = []
    for inputPath in inputPaths[i]:
        # this call assumes transaction version 1
        prevoutscript = bytearray(redeemScripts[i].decode('hex')) if inputType[i] == "scripthash" else prevoutScriptPubkey[i]
        app.startUntrustedTransaction(newTx, i, trustedInputs, prevoutscript, decodedTxn["version"])
        newTx = False
        outputData = app.finalizeInput("DUMMY", -1, -1, donglePath, spendTxn)
        # Provide the key that is signing the input
        signature.append(app.untrustedHashSign(donglePath+inputPath, "", decodedTxn["locktime"], 0x01))
    signatures.append(signature)

inputScripts = []
for i in range(len(signatures)):
    if inputType[i] == "pubkey":
        inputScripts.append(get_p2pk_input_script(signatures[i][0]))
    elif inputType[i] == "pubkeyhash":
        inputScripts.append(get_regular_input_script(signatures[i][0], inputPubKey[i]))
    elif inputType[i] == "scripthash":
        inputScripts.append(get_p2sh_input_script(bytearray(redeemScripts[i].decode('hex')), signatures[i]))
    else:
        raise Exception("only p2pkh, non-segwit p2sh and p2pk currently supported")

trustedInputsAndInputScripts = []
for trustedInput, inputScript in zip(trustedInputs, inputScripts):
    trustedInputsAndInputScripts.append([trustedInput['value'], inputScript, inputSeq[i]])

transaction = format_transaction(outputData['outputData'], trustedInputsAndInputScripts, decodedTxn["version"], decodedTxn["locktime"])
transaction = ''.join('{:02x}'.format(x) for x in transaction)

print("*** Finalized transaction ***")
print(transaction)
print("*** Feerate ***")
response = raw_input("Send transaction? Y/n\n")
if response == "Y":
    print(bitcoin.call("sendrawtransaction", transaction))
else:
    print("Transaction not sent.")
