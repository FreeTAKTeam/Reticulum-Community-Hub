# Fix RCH issue 247

Remove incorrect RCH-owned transport strategies, without compatibility shims. Follow PLAN.md. LXMF-rs SDK/daemon is the routing and admitted-delivery truth owner; RCH owns application recipients and its outgoing queue. Completion requires code removal, destination-keyed SDK path operations, history-independent regression evidence, daemon evidence and required local checks, followed by a pushed PR.
