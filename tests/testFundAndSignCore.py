import sys
from btchip.btchip import *
from btchip.btchipUtils import *
from bitcoin.rpc import Proxy
import bitcoin
import sys
import struct
from pdb import set_trace

# This script will create a funded transaction from the wallet and sign
# This script requires you be running hdwatchonly(https://github.com/bitcoin/bitcoin/pull/9728)
# as well as a patch to understand p2sh-nested p2wpkh outputs.
# You must also set the "donglePath" variable below to whichever account xpubkey you
# imported into your Core wallet.
#
# Currently no support for nested-p2sh p2wsh or raw segwit outputs
#
# Other dependencies:
# python-bitcoinlib
# btchip-python
# and of course a connected Ledger Nano S
# running the bitcoin app 1.1.8 or later

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

conf = ""
if len(sys.argv) > 6:
    conf = sys.argv[6]

destAddr = sys.argv[1]
amount = sys.argv[2]
bitcoin.SelectParams(network)

try:
    if conf != "":
        bitcoin = Proxy(btc_conf_file=conf)
    else:
        bitcoin = Proxy()
except:
    print("Make sure bitcoind is running.")
    sys.exit(-1)

smartfee = bitcoin.call("estimatesmartfee", block_target, "ECONOMICAL")

# Setup dongle
dongle = getDongle(True)
app = btchip(dongle)

# Create spending transaction, sending to destAddr
rawTxn = bitcoin.call("createrawtransaction", [], {destAddr:amount})

# Fund the transaction
# Inputs in this setup must be p2pkh and not coinbase transactions
fundoptions = {"includeWatching":True, "replaceable":True}
if "feerate" in smartfee:
    fundoptions["feeRate"] = str(smartfee)

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

has_segwit = False
has_legacy = False

# Get input transactions
rawInputs = []
inputTxids = []
inputVouts = []
inputAddrs = []
inputAmount = []
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
    inputAmount.append(decodedInput["vout"][input["vout"]]["value"])
    validata = bitcoin.validateaddress(inputAddrs[-1])
    if validata["isscript"] == True:
        if validata["script"] != "multisig" and validata["script"] != "witness_v0_keyhash":
            raise Exception("Only multisig and witness_v0_keyhash p2sh are currently supported")
        subpaths = []
        if validata["script"] == "multisig" and "addresses" in validata:
            inputType[-1] = "p2sh-multisig"
            for address in validata["addresses"]:
                subvalid = bitcoin.validateaddress(address)
                if "hdkeypath" in subvalid:
                    subpaths.append(subvalid["hdkeypath"][1:])
            inputPubKey.append("")
            has_legacy = True
        if validata["script"] == "witness_v0_keyhash" and "hdkeypath" in validata:
            inputType[-1] = "p2sh-witness_v0_keyhash"
            subpaths.append(validata["hdkeypath"][1:])
            inputPubKey.append(validata["pubkey"])
            has_segwit = True
        inputPaths.append(subpaths)
        redeemScripts.append(validata["hex"])

    elif "hdkeypath" not in validata:
        raise Exception("Can not find keypath from address. Not ours?")
    else:
        has_legacy = True
        inputPaths.append([validata["hdkeypath"][1:]])
        inputPubKey.append(validata["pubkey"])
        redeemScripts.append("")

    seq = format(input["sequence"], 'x')
    seq = seq.zfill(len(seq)+len(seq)%2)
    seq = bytearray(seq.decode('hex'))
    seq.reverse()
    seq = ''.join('{:02x}'.format(x) for x in seq)
    inputSeq.append(seq)

spendTxn = bytearray(fundTxn["hex"].decode('hex'))

prevoutScriptPubkey = []
outputData = ""
trustedInputs = []
signatures = [[]]*len(inputTxids)

# To sign mixed segwit/non-segwit inputs, you just sign in both modes, once each

# Sign for legacy inputs
if has_legacy:
    # Compile trusted inputs for non-segwit signing
    for i in range(len(inputTxids)):
        inputTransaction = bitcoinTransaction(bytearray(rawInputs[i].decode('hex')))
        trustedInputs.append(app.getTrustedInput(inputTransaction, inputVouts[i]))
        trustedInputs[-1]["sequence"] = inputSeq[i]
        prevoutScriptPubkey.append(inputTransaction.outputs[inputVouts[i]].script)

    newTx = True
    # Now we legacy sign the transaction, input by input
    for i in range(len(inputTxids)):
        if inputType[i] == "p2sh-witness_v0_keyhash":
            continue
        signature = []
        for inputPath in inputPaths[i]:
            prevoutscript = bytearray(redeemScripts[i].decode('hex')) if inputType[i] == "p2sh-multisig" else prevoutScriptPubkey[i]
            app.startUntrustedTransaction(newTx, i, trustedInputs, prevoutscript, decodedTxn["version"])
            newTx = False
            outputData = app.finalizeInput("DUMMY", -1, -1, donglePath+changePath, spendTxn)
            # Provide the key that is signing the input
            signature.append(app.untrustedHashSign(donglePath+inputPath, "", decodedTxn["locktime"], 0x01))
        signatures[i] = signature

segwitInputs = []
# Sign segwit inputs
if has_segwit:
    # Build segwit inputs
    for i in range(len(inputTxids)):
        txid = bytearray(inputTxids[i].decode('hex'))
        txid.reverse()
        vout = inputVouts[i]
        amount = inputAmount[i]
        segwitInputs.append({"value":txid+struct.pack("<I", vout)+struct.pack("<Q", int(amount*100000000)), "witness":True, "sequence":inputSeq[i]})

    newTx = True
    # Process them front with all inputs
    prevoutscript = bytearray()
    for i in range(len(inputTxids)):
        app.startUntrustedTransaction(newTx, i, segwitInputs, prevoutscript, decodedTxn["version"])
        newTx = False

    # Then finalize, and process each input as a single-input transaction
    outputData = app.finalizeInput("DUMMY", -1, -1, donglePath+changePath, spendTxn)
    # Sign segwit-style nested keyhashes
    for i in range(len(inputTxids)):
        if inputType[i] != "p2sh-witness_v0_keyhash":
            continue
        signature = []
        for inputPath in inputPaths[i]:
            # For p2wpkh, we need to convert the script into something sensible to the ledger:
            # OP_DUP OP_HASH160 <program> OP_EQUALVERIFY OP_CHECKSIG
            prevoutscript = redeemScripts[i][4:] #cut off version and push bytes
            prevoutscript = bytearray(("76a914"+prevoutscript+"88ac").decode("hex"))
            
            app.startUntrustedTransaction(newTx, 0, [segwitInputs[i]], prevoutscript, decodedTxn["version"])
            signature.append(app.untrustedHashSign(donglePath+inputPath, "", decodedTxn["locktime"], 0x01))
        signatures[i] = signature


witnessesToInsert = [bytearray(0x00)]*len(signatures)
inputScripts = []
for i in range(len(signatures)):
    if inputType[i] == "pubkey":
        inputScripts.append(get_p2pk_input_script(signatures[i][0]))
    elif inputType[i] == "pubkeyhash":
        inputScripts.append(get_regular_input_script(signatures[i][0], inputPubKey[i]))
    elif inputType[i] == "p2sh-multisig":
        inputScripts.append(get_p2sh_multisig_input_script(bytearray(redeemScripts[i].decode('hex')), signatures[i]))
    elif inputType[i] == "p2sh-witness_v0_keyhash":
        # Just the redeemscript, we need to insert the signature to witness
        inputScript = bytearray()
        write_pushed_data_size(bytearray(redeemScripts[i].decode('hex')), inputScript)
        inputScript.extend(bytearray(redeemScripts[i].decode('hex')))
        inputScripts.append(inputScript)
        witnessesToInsert[i] = get_witness_keyhash_witness(signatures[i][0], inputPubKey[i])

    else:
        raise Exception("only p2pkh, p2sh(multisig and p2wpkh) and p2pk currently supported")

witness = bytearray()
if has_segwit:
    for i in range(len(witnessesToInsert)):
        writeVarint((2 if len(witnessesToInsert[i]) != 0 else 0), witness)#push two items to stack
        if len(witnessesToInsert[i]) != 0:
            witness.extend(witnessesToInsert[i])

processed_inputs = segwitInputs if has_segwit else trustedInputs
process_trusted = not has_segwit
    

trustedInputsAndInputScripts = []
for processedInput, inputScript in zip(processed_inputs, inputScripts):
    trustedInputsAndInputScripts.append([processedInput['value'], inputScript, inputSeq[i]])

transaction = format_transaction(outputData['outputData'], trustedInputsAndInputScripts, decodedTxn["version"], decodedTxn["locktime"], process_trusted, witness)
transaction = ''.join('{:02x}'.format(x) for x in transaction)

print("*** Presigned transaction ***")
print(fundTxn["hex"])
print("*** Finalized transaction ***")
print(transaction)
print("*** Feerate ***")
print(str(fundTxn["fee"]*100000000/(len(transaction)/2)).split(".")[0] + " satoshis/byte")
response = raw_input("Send transaction? Y/n\n")
if response == "Y":
    try:
        print(bitcoin.call("sendrawtransaction", transaction))
    except:
        # in case of error I want to take a look
        set_trace()
else:
    print("Transaction not sent.")

