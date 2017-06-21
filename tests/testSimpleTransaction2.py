
from btchip.btchip import *
from btchip.btchipUtils import *

# Run this to sign transactions withe ledger api

# normal transaction serialized, to prove input amount
# TODO Verify paths so I can sign both inputs
# one input, first output is m/0'/0'/0, second output is m/0'/0'/1
# ./src/bitcoin-cli createrawtransaction '[{"txid":"a761fedaabf97a003fc50fe971010c417a36ba357b5595209885205893056dd9", "vout":0}]' '{"1KjFQFiwiLjMtB7KUsnEyUVzytjTSKHdv":1, "1AR7VcSLsC9kUxi4USvDz3dTEVNqu8E4en":100000}'
# added junk scriptsig to make it parse right
UTX = bytearray("0200000001d96d0593582085982095557b35ba367a410c0171e90fc53f007af9abdafe61a7000000001976a91467488914388639305b03e0a7305e545dcb33148a88acffffffff0200e1f505000000001976a914038ac1210739155c865f9bed9df480d137ec8a6a88ac00a0724e180900001976a91467488914388639305b03e0a7305e545dcb33148a88ac00000000".decode('hex'))
UTXO_INDEX = 1
UTX_TXID = "ab210af364fc14505b04155ce6f55fa04230f74e1ab04a1bd7b010822cbcc722"
ADDRESS = "1BTChipvU14XH6JdRiK9CaenpJ2kJR9RnC"
AMOUNT = "99999.0"
FEES = "1.0"

# Create spending transaction. Second address is self-owned but should be non-change
# ./src/bitcoin-cli createrawtransaction '[{"txid":"ab210af364fc14505b04155ce6f55fa04230f74e1ab04a1bd7b010822cbcc722", "vout":1}, {"txid":"ab210af364fc14505b04155ce6f55fa04230f74e1ab04a1bd7b010822cbcc722", "vout":0}]' '{"1Fy2qG4NaJfgCmqDLfgTRmofkrAki3zbiC":90000, "1L1MnRpFyFWNdNh2ECPCJEQ95L41Gj7me8":100}'
SPEND_TX = bytearray("020000000122c7bc2c8210b0d71b4ab01a4ef73042a05ff5e65c15045b5014fc64f30a21ab0100000000ffffffff020090cd792f0800001976a914a42a958ba0f8ca28344ab74ee4a04d934127834b88ac00e40b54020000001976a914d07bbd264d8a0d5f65b9a9f1790f455d7cf48edf88ac00000000".decode('hex'))

# Steps to integtrate
# 1) bitcoind exports all input transactions
# 2) bitcoind exports unsigned transaction
# 3) getTrustedInput for all input transactions
# 4) startUntrustedTransaction with list of now-trusted inputs
# 5) finalizeInput with dest addr, amount, fee, path
# 6) untrustedHashSign
# 7) put transaction back together

# Optional setup
dongle = getDongle(True)
app = btchip(dongle)

# Get the public key and compress it
publicKey = compress_public_key(app.getWalletPublicKey("0'/0'/0")['publicKey'])
# Get the trusted input associated to the UTXO
transaction = bitcoinTransaction(UTX)
# scriptpubkey of the prevout
outputScript = transaction.outputs[UTXO_INDEX].script
# Trusted means it figures out the value of the output via this call
# Do this for each input in order
trustedInput = app.getTrustedInput(transaction, UTXO_INDEX)
# Start composing the transaction
# Need to do this 
app.startUntrustedTransaction(True, 0, [trustedInput], outputScript)
outputData = app.finalizeInput("", -1, -1, "0'/0'/0/0/0", SPEND_TX)
signature = app.untrustedHashSign("0'/0'/0")

#outputScript2 = transaction.outputs[UTXO_INDEX-1].script
#trustedInput2 = app.getTrustedInput(transaction, UTXO_INDEX-1)
#app.startUntrustedTransaction(False, 1, [trustedInput2], outputScript2)
#                              destaddr               changepath
#outputData2 = app.finalizeInput("", -1, -1, "0'/0'/0/0/0", SPEND_TX)
#signature2 = app.untrustedHashSign("0'/0'/1")
inputScript = get_regular_input_script(signature, publicKey)
transaction = format_transaction(outputData['outputData'], [ [ trustedInput['value'], inputScript] ])
print "Generated transaction : " + str(transaction).encode('hex')

