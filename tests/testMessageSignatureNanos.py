"""
*******************************************************************************    
*   BTChip Bitcoin Hardware Wallet Python API
*   (c) 2014 BTChip - 1BTChip7VfTnrPra5jqci7ejnMguuHogTn
*   
*  Licensed under the Apache License, Version 2.0 (the "License");
*  you may not use this file except in compliance with the License.
*  You may obtain a copy of the License at
*
*      http://www.apache.org/licenses/LICENSE-2.0
*
*   Unless required by applicable law or agreed to in writing, software
*   distributed under the License is distributed on an "AS IS" BASIS,
*   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
*  See the License for the specific language governing permissions and
*   limitations under the License.
********************************************************************************
"""

from btchip.btchip import *
from btchip.btchipUtils import *
import base64

MESSAGE = raw_input("Message to sign:\n")

keyPath = raw_input("Key path to use:\n")[2:]

# Optional setup
dongle = getDongle(True)
app = btchip(dongle)

# Start signing
print(app.getWalletPublicKey(keyPath))
app.signMessagePrepare(keyPath, MESSAGE)
# Compute the signature
signature = app.signMessageSign()

rLength = signature[3]
r = signature[4 : 4 + rLength]
sLength = signature[4 + rLength + 1]
s = signature[4 + rLength + 2:]
if rLength == 33:
    r = r[1:]
if sLength == 33:
    s = s[1:]
r = str(r)
s = str(s)

sig = chr(27 + 4 + (signature[0] & 0x01)) + r + s

print("Address:\n" + app.getWalletPublicKey(keyPath)["address"])
print("Signature:\n" + base64.b64encode(sig))
