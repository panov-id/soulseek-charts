# Protocol notes

Behaviour of the Soulseek network found by experiment while building this
project. None of it appears in the protocol documentation maintained by the
Nicotine+ project, which is otherwise the reference for message formats.

Sources for the formats themselves:

- https://nicotine-plus.org/doc/SLSKPROTOCOL.html
- https://aioslsk.readthedocs.io/en/latest/SOULSEEK.html
- https://www.slsknet.org/157.html

## 1. The server gates the distributed network on client version

An unrecognised client major version logs in successfully, receives the room
list, privileged users and server settings, and answers to `CheckPrivileges`
and `WatchUser` — but **`PossibleParents` (102) never arrives**, so the node
never joins the search tree and sees nothing.

Announcing a version the server knows produces candidates within ten seconds.

This is the single largest obstacle to writing a new client honestly, and it has
no documented legitimate solution.

## 2. The full post-login sequence is mandatory

Logging in is not enough. Until the node announces itself properly, the server
does not treat it as fully online and offers no parents:

    CheckPrivileges (92)
    SetWaitPort (2)
    SetStatus (28)          <- the one most easily missed
    SharedFoldersFiles (35)
    WatchUser (5, own name)
    HaveNoParent (71, true)
    BranchRoot (127, own name)
    BranchLevel (126, 0)
    AcceptChildren (100)

plus a periodic `ServerPing` (32).

## 3. Candidate addresses decode from the high byte

The IP in `PossibleParents` is a `uint32`. Decoded little-endian, the first
octet of the address ends up in the **high** byte:

    address>>24, address>>16, address>>8, address

Reading it the other way round produces plausible-looking but nonexistent
networks, and every connection times out.

## 4. Keep exactly one parent

Racing several candidates and keeping them all is tempting, and wrong. Every
parent relays the same queries, so counts inflate by the number of parents —
measured at roughly five times with three parents, once retries are included.

Adopt the first candidate that actually delivers a search, drop the rest.

## 5. The server goes quiet once a parent is adopted

After `HaveNoParent(false)`, the server stops sending candidates, and searches
arrive from the parent rather than from the server. The server connection can
then legitimately sit silent for a long time.

A short read deadline on that socket therefore kills healthy connections on a
timer. Use TCP keep-alive and the failure of the periodic ping to detect a dead
peer instead. Also reset any reconnect backoff after a successful session, or it
ratchets to its cap and stays there.

## 6. Search traffic is a full broadcast

Streams delivered by parents at different depths are the same. Measured across
three parents at branch levels 4, 6 and 6 over four minutes:

- 11 018 distinct queries in the common window
- pairwise Jaccard 0.995–0.999
- 99.4% arrived from all three parents, 0.3% from exactly one

So position in the tree affects latency, not coverage, and one node sees
essentially everything. Note this was measured within one branch root at a time;
several roots exist and change over the course of a day.

## 7. Wishlist searches are rate-limited by the server

`WishlistInterval` (104) is almost always 12 minutes, or 2 for privileged
accounts. Automated re-searching cannot go faster than the server allows, which
also means periodic repeats in the stream are not necessarily popularity.
