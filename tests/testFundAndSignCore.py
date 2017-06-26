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

if len(sys.argv) < 3:
    print("Please enter an address and amount to send")
    sys.exit(-1)

network = 'testnet'
if len(sys.argv) > 3:
    # arg can be "testnet", "mainnet", or "regtest"
    network = sys.argv[3]

# Assume standard BIP44 structure to xpub in Core
# if this is wrong signing will fail.
donglePath = "m/44'/0'/0'"[2:]
if len(sys.argv) > 4:
    donglePath = sys.argv[4][2:]

# Default wait of 6 blocks
block_target = 6
if len(sys.argv) > 5:
    block_target = int(sys.argv[5])

destAddr = sys.argv[1]
amount = sys.argv[2]
bitcoin.SelectParams(network)

try:
    bitcoin = Proxy()
except:
    print("Make sure bitcoind is running.")
    sys.exit(-1)

smartfee = bitcoin.call("estimatesmartfee", block_target, False)["feerate"]

# Setup dongle
dongle = getDongle(True)
app = btchip(dongle)

# Create spending transaction, sending to destAddr
rawTxn = bitcoin.call("createrawtransaction", [], {destAddr:amount})

# Fund the transaction
# Inputs in this setup must be p2pkh and not coinbase transactions
fundoptions = {"includeWatching":True}
if smartfee > -1:
    fundoptions["feeRate"] = smartfee

fundTxn = bitcoin.call("fundrawtransaction", rawTxn, fundoptions)
# Grab input transactions
decodedTxn = bitcoin.call("decoderawtransaction", fundTxn["hex"])

# Random changePath in case there is no change
changePath = "0'/0'/0'/0'"
if fundTxn["changepos"] == -1:
    changeInfo = None
else:
    changeInfo = bitcoin.validateaddress(decodedTxn["vout"][fundTxn["changepos"]]["scriptPubKey"]["addresses"][0])
    # Drop "m"
    changePath = changeInfo["hdkeypath"][1:]

# Get input transactions
rawInputs = []
inputTxids = []
inputVouts = []
inputAddrs = []
inputPaths = []
inputPubKey = []
inputSeq = []
for input in decodedTxn["vin"]:
    walletInput = bitcoin.call("gettransaction", input["txid"])
    decodedInput = bitcoin.call("decoderawtransaction", walletInput["hex"])
    rawInputs.append(walletInput["hex"])
    inputTxids.append(input["txid"])
    inputVouts.append(input["vout"])
    inputAddrs.append(decodedInput["vout"][input["vout"]]["scriptPubKey"]["addresses"][0])
    validata = bitcoin.validateaddress(inputAddrs[-1])
    inputPaths.append(validata["hdkeypath"][1:])
    inputPubKey.append(validata["pubkey"])
    seq = format(input["sequence"], 'x')
    seq = seq.zfill(len(seq)+len(seq)%2)
    inputSeq.append(seq)

spendTxn = bytearray(fundTxn["hex"].decode('hex'))

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

# Now we sign the transaction, input by input
for i in range(len(inputTxids)):
    # this call assumes transaction version 1
    app.startUntrustedTransaction(i == 0, i, trustedInputs, prevoutScriptPubkey[i], decodedTxn["version"])
    outputData = app.finalizeInput("DUMMY", -1, -1, donglePath+changePath, spendTxn)
    # Provide the key that is signing the input
    signatures.append(app.untrustedHashSign(donglePath+inputPaths[i], "", decodedTxn["locktime"], 0x01))

inputScripts = []
for i in range(len(signatures)):
    inputScripts.append(get_regular_input_script(signatures[i], inputPubKey[i]))

trustedInputsAndInputScripts = []
for trustedInput, inputScript in zip(trustedInputs, inputScripts):
    trustedInputsAndInputScripts.append([trustedInput['value'], inputScript, inputSeq[i]])

transaction = format_transaction(outputData['outputData'], trustedInputsAndInputScripts, decodedTxn["version"], decodedTxn["locktime"])
transaction = ''.join('{:02x}'.format(x) for x in transaction)

print("*** Presigned transaction ***")
print(fundTxn["hex"])
print("*** Finalized transaction ***")
print(transaction)
print("*** Feerate ***")
print(str(fundTxn["fee"]*100000000/(len(transaction)/2)).split(".")[0] + " satoshis/byte")
response = raw_input("Send transaction? Y/n\n")
if response == "Y":
    print(bitcoin.call("sendrawtransaction", transaction))
else:
    print("Transaction not sent.")
