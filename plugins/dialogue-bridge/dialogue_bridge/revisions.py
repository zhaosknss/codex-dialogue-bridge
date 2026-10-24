"""Scoped, replayable shared changes and recoverable proposal dispositions.

All work is local and model-free. A review intent records its exact semantic
input before applying a patch, so a crash between the shared revision and the
proposal disposition can resume without silently accepting different content.
"""
from copy import deepcopy

from .archive import thread_id
from .context import digest, nonempty


def _normalized_patch(payload):
    if not isinstance(payload, dict):
        raise ValueError("Shared update payload must be an object")
    result = deepcopy(payload)
    if "entries" in result:
        if not isinstance(result["entries"], list):
            raise ValueError("entries must be a list")
        for entry in result["entries"]:
            if not isinstance(entry, dict):
                raise ValueError("Each shared entry must be an object")
            sources = entry.get("sources", [])
            if not isinstance(sources, list):
                raise ValueError("Entry sources must be a list")
            normalized = []
            for source in sources:
                if not isinstance(source, dict) or "ref" not in source:
                    raise ValueError("Evidence requires original message references")
                normalized.append({k: source[k] for k in ("ref", "quote") if k in source})
            entry["sources"] = normalized
    return result


def _scope_check(context, payload, allowed, base_revision):
    """Check attribution scopes without consulting changed original text.

    An old committed request may replay after source text/targets change, but
    replay does not grant a caller access to a scope excluded by its current bind.
    """
    if type(base_revision) is not int or not 0 <= base_revision <= context.ledger.revision:
        raise ValueError("Read an existing current revision before saving")
    old = context.ledger.snapshot(at_revision=base_revision).state.get("understanding") or {}
    entries = {entry["key"]: entry for entry in old.get("entries", [])}
    source_scopes = {s["thread"]: s["scope"] for s in context.config["sources"]}
    for entry in payload.get("entries", []):
        if entry.get("scope") not in allowed:
            raise ValueError("Understanding entry is outside this chat's selected scope")
        if entry.get("key") in entries and entries[entry["key"]]["scope"] not in allowed:
            raise ValueError("Cannot replace an entry outside this chat's selected scope")
        for source in entry.get("sources", []):
            reference = source.get("ref")
            if not isinstance(reference, str) or source_scopes.get(reference.split("/", 1)[0]) not in allowed:
                raise ValueError("Evidence is outside this chat's selected scope")
    removed = payload.get("remove_keys", [])
    if not isinstance(removed, list):
        raise ValueError("remove_keys must be a list")
    for key in removed:
        if key not in entries or entries[key]["scope"] not in allowed:
            raise ValueError("Cannot remove an entry outside this chat's selected scope")
    return old


def shared_update(context, payload, actor, allowed):
    """Apply a sourced patch, replaying committed inputs before source revalidation."""
    from .runtime import _check_patch, _shared, _store
    actor = thread_id(actor)
    payload = _normalized_patch(payload)
    operation = nonempty(payload.get("operation_id"), "operation_id", 150)
    base = payload.get("expected_revision")
    previous = context.ledger.get_commit("context:" + actor + ":" + operation)
    old = _scope_check(context, payload, set(allowed), base)
    if not previous:
        _check_patch(context, payload, allowed)
    # Choose save/revise from the requested historical base, not today's state.
    # Context.save checks the original fingerprint before any source/document work.
    if old:
        result = context.revise(payload, actor=actor)
    else:
        if payload.pop("remove_keys", []):
            raise ValueError("There are no shared entries to remove yet")
        payload.setdefault("purpose", "Revisable understanding for the selected conversations and their work")
        result = context.save(payload, actor=actor)
    if not result.get("replayed"):
        _store(context).materialize(_shared(context))
    return result


def _visible_proposals(context, actor, allowed):
    from .runtime import _visible
    # The caller already resolved the current saved binding/requested selection.
    return _visible(context, actor, requested=sorted(allowed))["proposals"]


def _review_input(arguments):
    result = {"id": nonempty(arguments.get("id"), "id", 200), "decision": arguments.get("decision"),
              "reason": nonempty(arguments.get("reason", "Reviewed the proposal and its cited context"), "reason", 2000)}
    if result["decision"] not in {"accept", "reject"}:
        raise ValueError("decision must be accept or reject")
    for field in ("entries", "remove_keys", "coverage_token", "expected_revision", "document_sha256"):
        if field in arguments:
            result[field] = deepcopy(arguments[field])
    if "entries" in result:
        result["entries"] = _normalized_patch({"entries": result["entries"]})["entries"]
    return result


def review(context, store, actor, arguments, allowed):
    """Review with a durable exact intent and independent apply/resolve retries.

    A local UI operator retains its synthetic author identity. If that identity
    cannot resolve the scoped proposal, no intent or shared patch is committed.
    Plain external edits need a model's cited structured patch before adoption.
    """
    from agent_state_core import Record, Transition
    from .runtime import _check_patch, _shared
    actor = thread_id(actor)
    intent_input = _review_input(arguments)
    operation = nonempty(arguments.get("operation_id") or "review-" + digest(intent_input)[:32], "operation_id", 130)
    request = "bridge-review:" + actor + ":" + operation
    fingerprint = digest(intent_input)
    previous_intent = context.ledger.get_commit(request)
    if previous_intent and previous_intent.transition.records[0].body["input_digest"] != fingerprint:
        raise ValueError("Review operation_id was already committed with different content")
    proposal = next((p for p in _visible_proposals(context, actor, allowed) if p["id"] == intent_input["id"]), None)
    if proposal is None:
        raise ValueError("Unknown visible proposal within this chat's selected scope")
    # Check the DocumentStore's actual author's capability before patching. A
    # manager view can be wider than the synthetic operator's write scope.
    current_shared = _shared(context)
    native_scopes = store._permissions(current_shared, actor)
    readable = store.view(current_shared, actor=actor, scopes=sorted(set(allowed) & native_scopes))
    if not any(p["id"] == proposal["id"] for p in readable["proposals"]):
        return {"proposal_id": proposal["id"], "status": proposal["status"], "needs_source_review": True,
                "next": "An actual participant with this proposal's source scope must review it; no shared change was applied"}
    target_status = "accepted" if intent_input["decision"] == "accept" else "rejected"
    if previous_intent:
        intent = deepcopy(previous_intent.transition.records[0].body["intent"])
        if proposal["status"] not in {"pending", "deferred", target_status}:
            raise ValueError("Proposal was already resolved by a different review")
    else:
        if proposal["status"] not in {"pending", "deferred"}:
            raise ValueError("Proposal was already resolved; only its exact original review can replay")
        revision = context.ledger.revision
        supplied_revision = intent_input.get("expected_revision", revision)
        if type(supplied_revision) is not int or supplied_revision != revision:
            raise ValueError("Read the current revision before reviewing the proposal")
        coverage = context.coverage()["token"]
        supplied_coverage = intent_input.get("coverage_token", coverage)
        if supplied_coverage != coverage:
            raise ValueError("History coverage changed before the review")
        entries = intent_input.get("entries", proposal.get("entries", []))
        removed = intent_input.get("remove_keys", proposal.get("remove_keys", []))
        patch = None
        chat_adoption = None
        if target_status == "accepted":
            target = proposal.get("target_key", "")
            if proposal.get("type") == "operator_chat_edit" and target.startswith("chats/") and target.endswith(".md"):
                owner = target[6:-3]
                documents = context.ledger.snapshot().state.get("dialogue_documents", {}).get("chats", {})
                document = documents.get(owner)
                if actor != owner or not document or document["author_thread"] != owner or document["revision"] <= proposal["revision"]:
                    return {"proposal_id": proposal["id"], "status": "pending", "needs_source_review": True,
                            "next": "The owning chat can reconsider this correction, save its own revised document and then accept the proposal"}
                if entries or removed:
                    raise ValueError("Review a chat-document correction separately from a shared-entry revision")
                chat_adoption = {"owner_thread": owner, "revision": document["revision"], "document": target,
                                 "meaning": "The owning chat reports adoption in its newer document; interpretation quality remains reviewable"}
            elif not entries and not removed:
                return {"proposal_id": proposal["id"], "status": "pending", "needs_source_review": True,
                        "next": "Interpret the edited text against original evidence and supply sourced entries before acceptance"}
            if chat_adoption is None:
                patch = _normalized_patch({"entries": entries, "remove_keys": removed})
                _scope_check(context, patch, set(allowed), revision)
                _check_patch(context, patch, allowed)
                if any(not e.get("sources") or any("quote" not in s for s in e["sources"]) for e in patch["entries"]):
                    raise ValueError("Accepted shared entries require original message quotations")
                patch.update(operation_id=operation + "-apply", expected_revision=revision + 1,
                             coverage_token=coverage, reason=intent_input["reason"])
                if "document_sha256" in intent_input:
                    patch["document_sha256"] = intent_input["document_sha256"]
        intent = {"proposal_id": proposal["id"], "actor": actor, "status": target_status,
                  "reason": intent_input["reason"], "patch": patch,
                  "chat_adoption": chat_adoption,
                  "shared_digest": digest(current_shared["entries"]), "coverage_token": coverage}
        reviews = deepcopy(context.ledger.snapshot().state.get("bridge_review_intents", {}))
        reviews[request] = intent
        context.ledger.commit(Transition(updates={"bridge_review_intents": reviews},
            records=(Record("bridge_review_intent", {"input_digest": fingerprint, "intent": intent}, (actor,)),)),
            expected_revision=revision, request_id=request)
    update = None
    if intent["patch"] is not None:
        patch = deepcopy(intent["patch"])
        previous_apply = context.ledger.get_commit("context:" + actor + ":" + patch["operation_id"])
        if previous_apply:
            # Rebuild Context's original save envelope at its actual old base.
            # That path validates exact content before touching today's evidence.
            patch["expected_revision"] = previous_apply.revision - 1
        else:
            if digest(_shared(context)["entries"]) != intent["shared_digest"] or context.coverage()["token"] != intent["coverage_token"]:
                raise ValueError("Shared context or evidence changed since the review intent; re-review before applying")
            # Unrelated Ledger commits can move the CAS position safely while
            # the selected understanding and source coverage remain identical.
            patch["expected_revision"] = context.ledger.revision
        update = shared_update(context, patch, actor, allowed)
    resolve_request = "documents:" + actor + ":" + operation + "-resolve"
    previous_resolve = context.ledger.get_commit(resolve_request)
    result = store.resolve(actor, proposal["id"], intent["status"], intent["reason"],
                           operation_id=operation + "-resolve",
                           expected_revision=previous_resolve.revision - 1 if previous_resolve else context.ledger.revision)
    store.materialize(_shared(context))
    return {**result, "shared_update": update, "chat_adoption": intent.get("chat_adoption")}


def acknowledge(context, actor, arguments, allowed):
    """Record an actor-reported stage without claiming verified understanding."""
    from agent_state_core import Record, Transition
    from .runtime import _UI_ACTOR, _check_sources
    actor = thread_id(actor or _UI_ACTOR)
    ident = nonempty(arguments.get("id"), "id", 200)
    stage = arguments.get("stage", "read")
    if stage not in {"received", "read", "replied", "adopted"}:
        raise ValueError("stage must be received, read, replied or adopted")
    evidence = deepcopy(arguments.get("evidence", {}))
    if not isinstance(evidence, dict):
        raise ValueError("Processing evidence must be an object")
    if stage in {"replied", "adopted"} and not evidence:
        raise ValueError("Reply/adoption must include evidence of the actual subsequent work")
    value = {"id": ident, "actor": actor, "stage": stage, "evidence": evidence,
             "meaning": "Actor-reported processing stage; receipt alone is not verified understanding or adoption"}
    operation = nonempty(arguments.get("operation_id") or "receipt-" + digest(value), "operation_id", 150)
    request = "bridge-receipt:" + actor + ":" + operation
    previous = context.ledger.get_commit(request)
    fingerprint = digest(value)
    if previous and previous.transition.records[0].body["input_digest"] != fingerprint:
        raise ValueError("Receipt operation_id was already committed with different content")
    if not any(p["id"] == ident for p in _visible_proposals(context, actor, allowed)):
        raise ValueError("Unknown visible contribution within this chat's selected scope")
    if previous:
        return {**deepcopy(previous.transition.records[0].body["result"]), "replayed": True}
    # Original-source citations remain within the receiver's scope. Artifact
    # pointers are retained as reports and are never read or executed here.
    references = evidence.get("sources", [])
    if not isinstance(references, list):
        raise ValueError("Processing evidence sources must be a list")
    if "ref" in evidence:
        references = [evidence, *references]
    _check_sources(context, references, allowed)
    revision = context.ledger.revision
    if "expected_revision" in arguments and (type(arguments["expected_revision"]) is not int or arguments["expected_revision"] != revision):
        raise ValueError("Read the current revision before acknowledging")
    receipts = deepcopy(context.ledger.snapshot().state.get("bridge_receipts", {}))
    receipts.setdefault(actor, {})[ident] = value
    result = {**value, "revision": revision + 1}
    context.ledger.commit(Transition(updates={"bridge_receipts": receipts},
        records=(Record("bridge_receipt", {"input_digest": fingerprint, "result": result}, (actor,)),)),
        expected_revision=revision, request_id=request)
    return {**result, "replayed": False}
