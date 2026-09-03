# SPDX-License-Identifier: MIT
# shellcheck shell=bash
# Shell equivalent of bot_keys.py: BoTTube bot API keys from an out-of-repo file.
#
#   source "$(dirname "$0")/bot_keys.sh"
#   bot_keys_require sophia-elya laughtrack_larry   # exits the script if any is missing
#   curl -H "X-API-Key: $(bot_key sophia-elya)" ...
#
# File resolution: $BOTTUBE_BOT_KEYS_FILE, else /root/bottube/.bot_keys.env,
# else ~/.elyan-secrets/bottube-bot-keys.env. Format: BOT_KEY_<NAME>=bottube_sk_...
# where <NAME> is the agent name upper-cased, non-alphanumerics -> "_".
# Never echo key values; `bot_keys_list` prints variable names only.

bot_keys_file() {
    if [ -n "${BOTTUBE_BOT_KEYS_FILE:-}" ]; then
        printf '%s\n' "$BOTTUBE_BOT_KEYS_FILE"
        return
    fi
    local f
    for f in /root/bottube/.bot_keys.env "$HOME/.elyan-secrets/bottube-bot-keys.env"; do
        if [ -f "$f" ]; then
            printf '%s\n' "$f"
            return
        fi
    done
    printf '%s\n' /root/bottube/.bot_keys.env
}

bot_key_var() {
    printf 'BOT_KEY_%s\n' "$(printf '%s' "$1" | tr -c 'A-Za-z0-9' '_' | tr 'a-z' 'A-Z')"
}

_BOT_KEYS_FILE="$(bot_keys_file)"
if [ -f "$_BOT_KEYS_FILE" ]; then
    # Load NAME=value lines into the environment without leaving allexport on.
    case $- in *a*) _bot_keys_had_a=1 ;; *) _bot_keys_had_a=0 ;; esac
    set -a
    # shellcheck disable=SC1090
    . "$_BOT_KEYS_FILE"
    [ "$_bot_keys_had_a" = 1 ] || set +a
    unset _bot_keys_had_a
fi

# bot_key AGENT_NAME -> prints the key; returns 1 (message on stderr) if unset.
bot_key() {
    local var val
    var="$(bot_key_var "$1")"
    val="${!var:-}"
    if [ -z "$val" ]; then
        echo "bot_key: $var is not set (agent '$1'); expected in $_BOT_KEYS_FILE" >&2
        return 1
    fi
    printf '%s' "$val"
}

# bot_keys_require NAME... -> exit 1 before doing any work if a key is missing.
bot_keys_require() {
    local n missing=0
    for n in "$@"; do
        bot_key "$n" >/dev/null || missing=1
    done
    if [ "$missing" -ne 0 ]; then
        echo "bot_keys: missing bot keys, aborting (see bottube-bot-keys.env.example)" >&2
        exit 1
    fi
}

bot_keys_list() {
    [ -f "$_BOT_KEYS_FILE" ] || return 1
    grep -oE '^(export[[:space:]]+)?BOT_KEY_[A-Za-z0-9_]+' "$_BOT_KEYS_FILE" | sed -E 's/^export[[:space:]]+//'
}
