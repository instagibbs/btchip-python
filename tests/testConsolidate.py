import sys
from btchip.btchip import *
from btchip.btchipUtils import *
from bitcoin.rpc import Proxy
import bitcoin
from decimal import *

if len(sys.argv) < 7:
    print("Please give: address network derivation_path conf_target consolidation_min consolidation_max")
    sys.exit(-1)

address = sys.argv[1]
network = sys.argv[2]
donglePath = sys.argv[3][2:]
block_target = int(sys.argv[4])
consolidateMin = Decimal(sys.argv[5])
consolidateMax = Decimal(sys.argv[6])
    
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

keydata = bitcoin.call("validateaddress", address)
if "hdkeypath" in keydata:
    app.getWalletPublicKey(donglePath+keydata["hdkeypath"][1:], True)
else:
    print("Wallet doesn't own destination address, exiting.")
    sys.exit(-1)

bitcoin.call("lockunspent", True)

# Get change address, amount you're sending
lockedFunds = []
destAmount = 0
unspent = bitcoin.call("listunspent", 0)
for utxo in unspent:
    if utxo["amount"] > consolidateMax or utxo["amount"] < consolidateMin:
        lockedFunds.append({"txid":utxo["txid"], "vout":utxo["vout"]})
    else:
        destAmount += utxo["amount"] 

assert(bitcoin.call("lockunspent", False, lockedFunds) == True)

print("Locked funds:" + str(lockedFunds))

# Create spending transaction, sending to destAddr
rawTxn = bitcoin.call("createrawtransaction", [], {address:str(destAmount)})

# Fund the transaction
fundoptions = {"includeWatching":True, "optIntoRbf":True, "subtractFeeFromOutputs":[0]}
if smartfee > -1:
    fundoptions["feeRate"] = str(smartfee)

fundTxn = bitcoin.call("fundrawtransaction", rawTxn, fundoptions)
# Grab input transactions
decodedTxn = bitcoin.call("decoderawtransaction", fundTxn["hex"])

# Unlock funds after funding
bitcoin.call("lockunspent", True, lockedFunds)

# No change, pass junk changepath
assert(fundTxn["changepos"] == -1)
changePath = "0'/0'/0'/0'"

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

newTx = True
# Now we sign the transaction, input by input
for i in range(len(inputTxids)):
    signature = []
    for inputPath in inputPaths[i]:
        # this call assumes transaction version 1
        prevoutscript = bytearray(redeemScripts[i].decode('hex')) if inputType[i] == "scripthash" else prevoutScriptPubkey[i]
        app.startUntrustedTransaction(newTx, i, trustedInputs, prevoutscript, decodedTxn["version"])
        newTx = False
        outputData = app.finalizeInput("DUMMY", -1, -1, donglePath+changePath, spendTxn)
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
