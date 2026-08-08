import json
import os
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


# =========================================================
# SMART WALLET HUNTER v1
# REAL SOLANA DATA
#
# Sources:
# - Helius
# - DEX Screener
#
# Output:
# - smart-wallet-data.json
# =========================================================

OUTPUT_FILE = Path("smart-wallet-data.json")

HELIUS_API_KEY = os.getenv(
    "HELIUS_API_KEY",
    ""
).strip()

HELIUS_RPC = (
    "https://mainnet.helius-rpc.com/"
    "?api-key="
    + urllib.parse.quote(HELIUS_API_KEY)
)

DEX_PROFILES = (
    "https://api.dexscreener.com/"
    "token-profiles/latest/v1"
)

DEX_BOOSTS = (
    "https://api.dexscreener.com/"
    "token-boosts/latest/v1"
)

DEX_TOKENS = (
    "https://api.dexscreener.com/"
    "tokens/v1/solana/"
)

ENHANCED_BASE = (
    "https://api.helius.xyz/v0/addresses/"
)

USER_AGENT = (
    "SmartWalletHunter/1.0"
)

MAX_TOKENS = 8
MAX_HOLDERS_PER_TOKEN = 6
MAX_WALLETS_TO_ANALYZE = 18
TRANSACTION_LIMIT = 40

NOW = datetime.now(
    timezone.utc
)

NOW_TS = int(
    NOW.timestamp()
)

SEVEN_DAYS = 7 * 24 * 60 * 60
SIX_HOURS = 6 * 60 * 60


# =========================================================
# TOKENS WE DO NOT COUNT AS MEMECOIN BUYS
# =========================================================

SOL_MINT = (
    "So11111111111111111111111111111111111111112"
)

USDC_MINT = (
    "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"
)

USDT_MINT = (
    "Es9vMFrzaCERmJfrF4H2FYD6EEQK9NV1J3o7YEMmQf2"
)

IGNORE_MINTS = {
    SOL_MINT,
    USDC_MINT,
    USDT_MINT,
}


# =========================================================
# HELPERS
# =========================================================

def log(message):
    print(
        "[SMART WALLET]",
        message,
        flush=True
    )


def safe_number(value, default=0):
    try:
        return float(value)
    except Exception:
        return default


def short_address(value):
    value = str(
        value or ""
    )

    if len(value) <= 12:
        return value

    return (
        value[:5]
        + "..."
        + value[-4:]
    )


def request_json(
    url,
    method="GET",
    payload=None,
    timeout=25
):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    }

    data = None

    if payload is not None:
        headers[
            "Content-Type"
        ] = "application/json"

        data = json.dumps(
            payload
        ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=data,
        headers=headers,
        method=method
    )

    try:
        with urllib.request.urlopen(
            request,
            timeout=timeout
        ) as response:

            raw = response.read()

            return json.loads(
                raw.decode("utf-8")
            )

    except Exception as error:
        log(
            f"Request failed: {url} -> {error}"
        )

        return None


def save_json(data):
    OUTPUT_FILE.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# =========================================================
# DISCOVER CURRENT SOLANA TOKENS
# =========================================================

def discover_tokens():

    log(
        "Discovering recent Solana tokens..."
    )

    candidates = {}

    sources = [
        (
            "DEX Latest Profiles",
            DEX_PROFILES
        ),
        (
            "DEX Latest Boosts",
            DEX_BOOSTS
        ),
    ]

    for source_name, url in sources:

        data = request_json(
            url
        )

        if isinstance(data, dict):
            data = [data]

        if not isinstance(data, list):
            continue

        for item in data:

            if not isinstance(
                item,
                dict
            ):
                continue

            chain = str(
                item.get(
                    "chainId",
                    ""
                )
            ).lower()

            if chain != "solana":
                continue

            mint = str(
                item.get(
                    "tokenAddress",
                    ""
                )
            ).strip()

            if not mint:
                continue

            if mint in IGNORE_MINTS:
                continue

            if mint not in candidates:

                candidates[mint] = {
                    "mint": mint,
                    "source": source_name,
                    "description": str(
                        item.get(
                            "description",
                            ""
                        )
                        or ""
                    )[:250],
                }

            if (
                len(candidates)
                >= MAX_TOKENS
            ):
                break

        if (
            len(candidates)
            >= MAX_TOKENS
        ):
            break

    tokens = list(
        candidates.values()
    )

    log(
        f"Found {len(tokens)} candidate tokens."
    )

    return tokens


# =========================================================
# DEX SCREENER TOKEN DETAILS
# =========================================================

def load_token_details(tokens):

    if not tokens:
        return {}

    addresses = ",".join(
        item["mint"]
        for item in tokens[:30]
    )

    url = (
        DEX_TOKENS
        + addresses
    )

    data = request_json(
        url
    )

    if not isinstance(
        data,
        list
    ):
        return {}

    result = {}

    for pair in data:

        if not isinstance(
            pair,
            dict
        ):
            continue

        base = (
            pair.get(
                "baseToken"
            )
            or {}
        )

        mint = str(
            base.get(
                "address",
                ""
            )
        )

        if not mint:
            continue

        existing = result.get(
            mint
        )

        liquidity = safe_number(
            (
                pair.get(
                    "liquidity"
                )
                or {}
            ).get(
                "usd"
            )
        )

        existing_liquidity = (
            safe_number(
                existing.get(
                    "liquidityUsd"
                )
            )
            if existing
            else -1
        )

        # Keep the most liquid pool.
        if (
            existing
            and
            existing_liquidity
            >= liquidity
        ):
            continue

        result[mint] = {
            "mint": mint,

            "symbol": str(
                base.get(
                    "symbol",
                    ""
                )
                or "TOKEN"
            ),

            "name": str(
                base.get(
                    "name",
                    ""
                )
                or ""
            ),

            "priceUsd": safe_number(
                pair.get(
                    "priceUsd"
                )
            ),

            "liquidityUsd": liquidity,

            "marketCap": safe_number(
                pair.get(
                    "marketCap"
                )
            ),

            "pairCreatedAt": pair.get(
                "pairCreatedAt"
            ),

            "dex": str(
                pair.get(
                    "dexId",
                    ""
                )
            ),

            "dexUrl": str(
                pair.get(
                    "url",
                    ""
                )
            ),
        }

    return result


# =========================================================
# HELIUS RPC
# =========================================================

def helius_rpc(
    method,
    params
):

    if not HELIUS_API_KEY:
        raise RuntimeError(
            "HELIUS_API_KEY is missing."
        )

    payload = {
        "jsonrpc": "2.0",
        "id": "smart-wallet-hunter",
        "method": method,
        "params": params,
    }

    result = request_json(
        HELIUS_RPC,
        method="POST",
        payload=payload
    )

    # Be gentle with free API limits.
    time.sleep(0.55)

    if not isinstance(
        result,
        dict
    ):
        return None

    if result.get("error"):
        log(
            "Helius RPC error: "
            + str(
                result.get(
                    "error"
                )
            )
        )

        return None

    return result.get(
        "result"
    )


# =========================================================
# GET HOLDERS
# =========================================================

def get_token_holders(mint):

    log(
        "Getting holders for "
        + short_address(mint)
    )

    result = helius_rpc(
        "getTokenAccounts",
        {
            "page": 1,
            "limit": 100,
            "displayOptions": {},
            "mint": mint,
        }
    )

    if not isinstance(
        result,
        dict
    ):
        return []

    accounts = result.get(
        "token_accounts",
        []
    )

    if not isinstance(
        accounts,
        list
    ):
        return []

    holders = []

    for account in accounts:

        if not isinstance(
            account,
            dict
        ):
            continue

        owner = str(
            account.get(
                "owner",
                ""
            )
        ).strip()

        amount = safe_number(
            account.get(
                "amount"
            )
        )

        if not owner:
            continue

        if amount <= 0:
            continue

        holders.append(
            {
                "owner": owner,
                "amount": amount,
            }
        )

    holders.sort(
        key=lambda item:
            item["amount"],
        reverse=True
    )

    unique = []
    seen = set()

    for holder in holders:

        owner = holder[
            "owner"
        ]

        if owner in seen:
            continue

        seen.add(
            owner
        )

        unique.append(
            holder
        )

        if (
            len(unique)
            >= MAX_HOLDERS_PER_TOKEN
        ):
            break

    return unique


# =========================================================
# HELIUS ENHANCED TRANSACTIONS
# =========================================================

def get_wallet_transactions(wallet):

    if not HELIUS_API_KEY:
        return []

    params = urllib.parse.urlencode(
        {
            "api-key":
                HELIUS_API_KEY,

            "limit":
                TRANSACTION_LIMIT,
        }
    )

    url = (
        ENHANCED_BASE
        + urllib.parse.quote(
            wallet,
            safe=""
        )
        + "/transactions?"
        + params
    )

    data = request_json(
        url
    )

    time.sleep(0.35)

    if not isinstance(
        data,
        list
    ):
        return []

    return data


# =========================================================
# ANALYZE WALLET TRANSACTION ACTIVITY
# =========================================================

def analyze_wallet(
    wallet,
    discovery_tokens,
    token_details
):

    transactions = (
        get_wallet_transactions(
            wallet
        )
    )

    swaps = []

    distinct_mints = set()

    for transaction in transactions:

        if not isinstance(
            transaction,
            dict
        ):
            continue

        tx_type = str(
            transaction.get(
                "type",
                ""
            )
        ).upper()

        transfers = transaction.get(
            "tokenTransfers",
            []
        )

        if isinstance(
            transfers,
            list
        ):
            for transfer in transfers:

                if not isinstance(
                    transfer,
                    dict
                ):
                    continue

                mint = str(
                    transfer.get(
                        "mint",
                        ""
                    )
                )

                if (
                    mint
                    and
                    mint not in IGNORE_MINTS
                ):
                    distinct_mints.add(
                        mint
                    )

        if tx_type == "SWAP":
            swaps.append(
                transaction
            )

    recent_swaps = []

    for transaction in swaps:

        timestamp = int(
            safe_number(
                transaction.get(
                    "timestamp"
                )
            )
        )

        if (
            timestamp
            and
            NOW_TS - timestamp
            <= SEVEN_DAYS
        ):
            recent_swaps.append(
                transaction
            )

    latest_buy = detect_latest_buy(
        wallet,
        swaps,
        token_details
    )

    signal_count = len(
        discovery_tokens
    )

    # =====================================================
    # ACTIVITY SCORE
    #
    # This is NOT a profit score.
    # We do not claim win rate or ROI yet.
    # =====================================================

       # =====================================================
    # SMART SCORE
    # =====================================================

    score = 20

    score += min(
        30,
        len(swaps) * 3
    )

    score += min(
        20,
        len(recent_swaps) * 4
    )

    score += min(
        15,
        len(distinct_mints) * 2
    )

    score += min(
        15,
        signal_count * 5
    )

    score = min(
        100,
        int(score)
    )


    # =====================================================
    # WHALE DETECTION
    #
    # Measure observed SOL sent from this wallet
    # during SWAP transactions.
    # =====================================================

    total_swap_sol = 0.0
    recent_swap_sol_7d = 0.0
    max_swap_sol = 0.0

    for transaction in swaps:

        native_transfers = transaction.get(
            "nativeTransfers",
            []
        )

        if not isinstance(
            native_transfers,
            list
        ):
            continue

        tx_out_lamports = 0.0

        for transfer in native_transfers:

            if not isinstance(
                transfer,
                dict
            ):
                continue

            from_wallet = str(
                transfer.get(
                    "fromUserAccount",
                    ""
                )
            )

            if from_wallet != wallet:
                continue

            tx_out_lamports += safe_number(
                transfer.get(
                    "amount"
                )
            )

        tx_out_sol = (
            tx_out_lamports
            / 1_000_000_000
        )

        total_swap_sol += tx_out_sol

        max_swap_sol = max(
            max_swap_sol,
            tx_out_sol
        )

        timestamp = int(
            safe_number(
                transaction.get(
                    "timestamp"
                )
            )
        )

        if (
            timestamp
            and NOW_TS - timestamp
            <= SEVEN_DAYS
        ):
            recent_swap_sol_7d += (
                tx_out_sol
            )


    # =====================================================
    # WALLET CLASSIFICATION
    #
    # Whale threshold:
    # 20 SOL in one observed swap
    # OR 100 SOL observed during 7 days.
    # =====================================================

    is_whale = (
        max_swap_sol >= 20
        or recent_swap_sol_7d >= 100
    )

    if is_whale and score >= 85:

        wallet_type = "SMART WHALE"
        tag = "Large Smart Money Activity"

    elif is_whale:

        wallet_type = "WHALE"
        tag = "Large Wallet Activity"

    elif score >= 85:

        wallet_type = "SMART WALLET"
        tag = "High Activity Candidate"

    elif score >= 70:

        wallet_type = "SMART WALLET"
        tag = "Early Activity Candidate"

    elif score >= 55:

        wallet_type = "ACTIVE WALLET"
        tag = "Active Wallet"

    else:

        wallet_type = "WATCHLIST"
        tag = "Wallet Under Review"


    return {
        "address": wallet,

        "shortAddress":
            short_address(wallet),

        "tag": tag,

        "walletType":
            wallet_type,

        "isWhale":
            is_whale,

        "smartScore":
            score,

        "swapCount":
            len(swaps),

        "recentSwaps7d":
            len(recent_swaps),

        "distinctTokens":
            len(distinct_mints),

        "discoverySignals":
            signal_count,

        "totalObservedSwapSol":
            round(
                total_swap_sol,
                4
            ),

        "recentSwapSol7d":
            round(
                recent_swap_sol_7d,
                4
            ),

        "maxSwapSol":
            round(
                max_swap_sol,
                4
            ),

        "discoveredOn":
            discovery_tokens,

        "latestBuy":
            latest_buy,
    }


# =========================================================
# DETECT MOST RECENT TOKEN RECEIVED DURING SWAP
# =========================================================

def detect_latest_buy(
    wallet,
    swaps,
    token_details
):

    sorted_swaps = sorted(
        swaps,
        key=lambda tx:
            int(
                safe_number(
                    tx.get(
                        "timestamp"
                    )
                )
            ),
        reverse=True
    )

    for transaction in sorted_swaps:

        timestamp = int(
            safe_number(
                transaction.get(
                    "timestamp"
                )
            )
        )

        transfers = transaction.get(
            "tokenTransfers",
            []
        )

        if not isinstance(
            transfers,
            list
        ):
            continue

        received = []

        for transfer in transfers:

            if not isinstance(
                transfer,
                dict
            ):
                continue

            to_wallet = str(
                transfer.get(
                    "toUserAccount",
                    ""
                )
            )

            mint = str(
                transfer.get(
                    "mint",
                    ""
                )
            )

            amount = safe_number(
                transfer.get(
                    "tokenAmount"
                )
            )

            if (
                to_wallet
                == wallet
                and mint
                and mint not in IGNORE_MINTS
                and amount > 0
            ):

                received.append(
                    (
                        mint,
                        amount
                    )
                )

        if not received:
            continue

        received.sort(
            key=lambda item:
                item[1],
            reverse=True
        )

        mint, amount = (
            received[0]
        )

        token = (
            token_details.get(
                mint,
                {}
            )
        )

        return {
            "mint": mint,

            "symbol": str(
                token.get(
                    "symbol",
                    ""
                )
                or short_address(
                    mint
                )
            ),

            "amount": amount,

            "timestamp": timestamp,

            "ageSeconds":
                max(
                    0,
                    NOW_TS - timestamp
                )
                if timestamp
                else None,
        }

    return None


# =========================================================
# DISCOVER CANDIDATE WALLETS
# =========================================================

def discover_wallets(
    tokens,
    token_details
):

    wallet_tokens = defaultdict(
        list
    )

    wallet_rank = defaultdict(
        int
    )

    for token in tokens:

        mint = token[
            "mint"
        ]

        details = (
            token_details.get(
                mint,
                {}
            )
        )

        symbol = str(
            details.get(
                "symbol",
                ""
            )
            or short_address(
                mint
            )
        )

        holders = (
            get_token_holders(
                mint
            )
        )

        log(
            f"{symbol}: "
            f"{len(holders)} candidate holders."
        )

        for index, holder in enumerate(
            holders
        ):

            wallet = holder[
                "owner"
            ]

            if mint not in wallet_tokens[
                wallet
            ]:

                wallet_tokens[
                    wallet
                ].append(
                    mint
                )

            # Higher ranked holder =
            # stronger discovery signal.
            wallet_rank[
                wallet
            ] += max(
                1,
                MAX_HOLDERS_PER_TOKEN
                - index
            )

    candidates = sorted(
        wallet_tokens.keys(),
        key=lambda wallet:
            (
                len(
                    wallet_tokens[
                        wallet
                    ]
                ),
                wallet_rank[
                    wallet
                ]
            ),
        reverse=True
    )

    return (
        candidates[
            :MAX_WALLETS_TO_ANALYZE
        ],
        wallet_tokens
    )


# =========================================================
# BUILD SMART MONEY ALERTS
# =========================================================

def build_alerts(wallets):

    token_activity = defaultdict(
        list
    )

    for wallet in wallets:

        latest = wallet.get(
            "latestBuy"
        )

        if not isinstance(
            latest,
            dict
        ):
            continue

        mint = latest.get(
            "mint"
        )

        timestamp = int(
            safe_number(
                latest.get(
                    "timestamp"
                )
            )
        )

        if not mint:
            continue

        if not timestamp:
            continue

        if (
            NOW_TS - timestamp
            > SIX_HOURS
        ):
            continue

        token_activity[
            mint
        ].append(
            {
                "wallet":
                    wallet[
                        "address"
                    ],

                "shortWallet":
                    wallet[
                        "shortAddress"
                    ],

                "score":
                    wallet[
                        "smartScore"
                    ],

                "timestamp":
                    timestamp,

                "symbol":
                    latest.get(
                        "symbol"
                    ),
            }
        )

    alerts = []

    for mint, entries in (
        token_activity.items()
    ):

        unique_wallets = {
            item["wallet"]
            for item in entries
        }

        if len(
            unique_wallets
        ) < 2:
            continue

        timestamps = [
            item["timestamp"]
            for item in entries
        ]

        window_seconds = (
            max(timestamps)
            - min(timestamps)
        )

        average_score = int(
            sum(
                item["score"]
                for item in entries
            )
            / len(entries)
        )

        alerts.append(
            {
                "mint": mint,

                "symbol":
                    entries[0].get(
                        "symbol"
                    ),

                "walletCount":
                    len(
                        unique_wallets
                    ),

                "windowMinutes":
                    max(
                        1,
                        round(
                            window_seconds
                            / 60
                        )
                    ),

                "confidence":
                    min(
                        100,
                        average_score
                        + min(
                            10,
                            len(
                                unique_wallets
                            ) * 2
                        )
                    ),

                "wallets": [
                    item[
                        "shortWallet"
                    ]
                    for item
                    in entries
                ],
            }
        )

    alerts.sort(
        key=lambda item:
            (
                item[
                    "walletCount"
                ],
                item[
                    "confidence"
                ]
            ),
        reverse=True
    )

    return alerts


# =========================================================
# RECENT BUYS
# =========================================================

def build_recent_buys(wallets):

    buys = []

    for wallet in wallets:

        latest = wallet.get(
            "latestBuy"
        )

        if not isinstance(
            latest,
            dict
        ):
            continue

        buys.append(
            {
                "wallet":
                    wallet[
                        "address"
                    ],

                "shortWallet":
                    wallet[
                        "shortAddress"
                    ],

                "smartScore":
                    wallet[
                        "smartScore"
                    ],

                "mint":
                    latest.get(
                        "mint"
                    ),

                "symbol":
                    latest.get(
                        "symbol"
                    ),

                "amount":
                    latest.get(
                        "amount"
                    ),

                "timestamp":
                    latest.get(
                        "timestamp"
                    ),

                "ageSeconds":
                    latest.get(
                        "ageSeconds"
                    ),
            }
        )

    buys.sort(
        key=lambda item:
            int(
                safe_number(
                    item.get(
                        "timestamp"
                    )
                )
            ),
        reverse=True
    )

    return buys[:15]


# =========================================================
# MAIN
# =========================================================

def main():

    log(
        "Starting Smart Wallet Hunter v1..."
    )

    if not HELIUS_API_KEY:

        raise RuntimeError(
            "HELIUS_API_KEY was not found. "
            "Add it to GitHub Actions secrets."
        )

    tokens = discover_tokens()

    token_details = (
        load_token_details(
            tokens
        )
    )

    candidates, wallet_tokens = (
        discover_wallets(
            tokens,
            token_details
        )
    )

    log(
        f"Analyzing {len(candidates)} wallets..."
    )

    analyzed_wallets = []

    for index, wallet in enumerate(
        candidates,
        start=1
    ):

        log(
            f"Wallet {index}/"
            f"{len(candidates)}: "
            f"{short_address(wallet)}"
        )

        analysis = analyze_wallet(
            wallet,
            wallet_tokens[
                wallet
            ],
            token_details
        )

        analyzed_wallets.append(
            analysis
        )

    analyzed_wallets.sort(
        key=lambda item:
            (
                item[
                    "smartScore"
                ],
                item[
                    "recentSwaps7d"
                ],
                item[
                    "swapCount"
                ]
            ),
        reverse=True
    )

    recent_buys = (
        build_recent_buys(
            analyzed_wallets
        )
    )

    alerts = (
        build_alerts(
            analyzed_wallets
        )
    )

    token_output = []

    for token in tokens:

        mint = token[
            "mint"
        ]

        details = (
            token_details.get(
                mint,
                {}
            )
        )

        token_output.append(
            {
                **token,
                **details,
            }
        )

    output = {
        "updatedAt":
            NOW.isoformat(),

        "version": 1,

        "mode": "REAL",

        "network": "Solana",

        "sources": [
            "Helius",
            "DEX Screener"
        ],

        "methodology": (
            "Smart Score v1 measures observed "
            "wallet activity and early-token signals. "
            "It is not a verified profit, ROI, or win-rate score."
        ),

        "stats": {
            "tokensScanned":
                len(tokens),

            "walletsAnalyzed":
                len(
                    analyzed_wallets
                ),

            "recentBuys":
                len(
                    recent_buys
                ),

            "smartMoneyAlerts":
                len(
                    alerts
                ),
        },

        "tokens":
            token_output,

        "wallets":
            analyzed_wallets,

        "recentBuys":
            recent_buys,

        "alerts":
            alerts,
    }

    save_json(
        output
    )

    log(
        "Finished."
    )

    log(
        f"Wallets analyzed: "
        f"{len(analyzed_wallets)}"
    )

    log(
        f"Recent buys: "
        f"{len(recent_buys)}"
    )

    log(
        f"Smart money alerts: "
        f"{len(alerts)}"
    )

    log(
        "Saved smart-wallet-data.json"
    )


if __name__ == "__main__":
    main()
