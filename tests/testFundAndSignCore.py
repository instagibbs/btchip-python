import sys
from btchip.btchip import *
from btchip.btchipUtils import *
from bitcoin.rpc import Proxy
import bitcoin
import sys

# This script will create a funded transaction from the wallet and sign

# https://ledgerhq.github.io/btchip-doc/bitcoin-technical-beta.html most up to date spec

network = 'mainnet'
if len(sys.argv) < 3:
    print("Please enter an address and amount to send")
    sys.exit(-1)

if len(sys.argv) > 3:
    # arg can be "testnet", "mainnet", or "regtest"
    network = sys.argv[3]

# Assume standard BIP44 structure
donglePath = "44'/0'/0'"

destAddr = sys.argv[1]
amount = sys.argv[2]
bitcoin.SelectParams(network)

try:
    bitcoin = Proxy()
except:
    print("Make sure bitcoind is running.")
    sys.exit(-1)

# Setup dongle
dongle = getDongle(True)
app = btchip(dongle)

# Create spending transaction, sending to destAddr
rawTxn = bitcoin.call("createrawtransaction", [], {destAddr:amount})

# Fund the transaction
# Inputs in this setup must be p2pkh and not coinbase transactions
fundTxn = bitcoin.call("fundrawtransaction", rawTxn, {"includeWatching":True})
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

spendTxn = bytearray(fundTxn["hex"].decode('hex'))

prevoutScriptPubkey = []
outputData = ""
trustedInputs = []
signatures = []
# Compile trusted inputs for later signing
for i in range(len(inputTxids)):
    inputTransaction = bitcoinTransaction(bytearray(rawInputs[i].decode('hex')))
    trustedInputs.append(app.getTrustedInput(inputTransaction, inputVouts[i]))
    prevoutScriptPubkey.append(inputTransaction.outputs[inputVouts[i]].script)

# Now we sign the transaction, input by input
for i in range(len(inputTxids)):
    app.startUntrustedTransaction(i == 0, i, trustedInputs, prevoutScriptPubkey[i])
    outputData = app.finalizeInput("DUMMY", -1, -1, donglePath+changePath, spendTxn)
    # Provide the key that is signing the input
    signatures.append(app.untrustedHashSign(donglePath+inputPaths[i], "", 0, 0x01))

inputScripts = []
for i in range(len(signatures)):
    inputScripts.append(get_regular_input_script(signatures[i], inputPubKey[i]))

trustedInputsAndInputScripts = []
for trustedInput, inputScript in zip(trustedInputs, inputScripts):
    trustedInputsAndInputScripts.append([trustedInput['value'], inputScript])

transaction = format_transaction(outputData['outputData'], trustedInputsAndInputScripts)
transaction = str(transaction).encode('hex')

print("*** Presigned transaction ***")
print(fundTxn["hex"])
print("*** Finalized transaction ***")
print(transaction)

