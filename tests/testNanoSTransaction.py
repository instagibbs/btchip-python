import sys
from btchip.btchip import *
from btchip.btchipUtils import *
import subprocess
import json

# TODO switch to AuthServiceProxy or something

if len(sys.argv) < 2:
    print("You must provide a path to a bitcoin-cli.")
    sys.exit(-1)

# Setup dongle
dongle = getDongle(True)
app = btchip(dongle)

donglePath = "0'/0'/"

# Get four pubkeys:
# Two to spend from
# One for "remote" destination
# One to receive as change
pubkeyInfo = []
publicKey = []
for i in range(4):
    pubkeyInfo.append(app.getWalletPublicKey(donglePath+str(i)))
    publicKey.append(compress_public_key(pubkeyInfo[-1]['publicKey']))

print("*** Addresses ***")
for i in range(4):
    print(pubkeyInfo[i]["address"])
print("*** \Addresses ***")

# Create input transaction that will have values validated.
bashCommand = [sys.argv[1], "createrawtransaction", "[{\"txid\":\"a761fedaabf97a003fc50fe971010c417a36ba357b5595209885205893056dd9\", \"vout\":0}]", "{\"" + pubkeyInfo[0]["address"] + "\":2, \"" + pubkeyInfo[1]["address"] + "\":100000}"]
inputTxn = subprocess.check_output(bashCommand)

# Insert junk scriptsig to sidestep firmware bug that expects non-0 scriptsig
inputTxn = inputTxn.replace("0000000000ffffffff", "000000001976a91467488914388639305b03e0a7305e545dcb33148a88acffffffff").strip()
print(inputTxn)

# Get TXID of this
bashCommand = [sys.argv[1], "decoderawtransaction", inputTxn]
TXID = json.loads(subprocess.check_output(bashCommand))["txid"]

# Create spending transaction, sending to key 2 and 3, latter of which will be considered change by
# firmware based on later calls
bashCommand = [sys.argv[1], "createrawtransaction",  "[{\"txid\":\"" + TXID + "\", \"vout\":0}, {\"txid\":\"" + TXID + "\", \"vout\":1}]", "{\"" + pubkeyInfo[2]["address"] + "\":2, \"" + pubkeyInfo[3]["address"] + "\":99999}"]

spendTxn = subprocess.check_output(bashCommand).strip()
spendTxn = bytearray(spendTxn.decode('hex'))

inputTransaction = bitcoinTransaction(bytearray(inputTxn.decode('hex')))

prevoutScriptPubkey = []
outputData = ""
trustedInputs = []
signatures = []
# Compile trusted inputs for later signing
for i in range(2):
    # Trusted means it figures out the value of the output via this call
    # to safely calculate fees
    trustedInputs.append(app.getTrustedInput(inputTransaction, i))
    # scriptpubkey of the prevout, we're assuming spending inputs in vout order
    prevoutScriptPubkey.append(inputTransaction.outputs[i].script)

# Now we sign the transaction, input by input
for i in range(2):
    # First argument is if this is the first time calling for the txn signing
    app.startUntrustedTransaction(i == 0, i, trustedInputs, prevoutScriptPubkey[i])
    # No need to pass first 3 args(address, amount, fee) if sending full txn.
    # Non-full API is deprecated regardless. Please annoy your local btchip to fix this.
    # Fourth argument is change path, which helps bypass confirming change output val
    outputData = app.finalizeInput("DUMMY", -1, -1, "0'/0'/"+str(len(pubkeyInfo)-1), spendTxn)
    # Provide the key that is signing the input
    signatures.append(app.untrustedHashSign("0'/0'/"+str(i)))


# TODO Do partial signing example

inputScripts = []
for i in range(2):
    inputScripts.append(get_regular_input_script(signatures[i], publicKey[i]))

trustedInputsAndInputScripts = []
for trustedInput, inputScript in zip(trustedInputs, inputScripts):
    trustedInputsAndInputScripts.append([trustedInput['value'], inputScript])

transaction = format_transaction(outputData['outputData'], trustedInputsAndInputScripts)
print "Generated transaction to send : " + str(transaction).encode('hex')

