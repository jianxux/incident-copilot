graph TD
    api[api]
    audit[audit]
    auth[auth]
    config[config]
    ratelimit[ratelimit]

    api --> audit
    audit --> config
    auth --> config
    ratelimit --> auth
    ratelimit --> config

    classDef critical fill:#f96,stroke:#333,stroke-width:2px