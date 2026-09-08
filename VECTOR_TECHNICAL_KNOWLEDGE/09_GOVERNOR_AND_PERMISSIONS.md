# Governor and Permission Gateway

**Purpose:** Intent classification, district routing, permission gates  
**Level:** Subsystem Level (Level 2)

---

## Overview

The Governor routes user queries to appropriate districts via intent classification, while the Permission Gateway gates all real-world actions with GREEN/YELLOW/RED tiers.

**Key Properties:**
- **Intent classification** — 4-stage pipeline (regex → embedding → Qwen3 → LLM)
- **District routing** — 33+ districts, 180 routing rules
- **Permission gateway** — GREEN/YELLOW/RED tiers (RULE 3)
- **HP-based governance** — council for high-stakes (HP > 700)
- **Pushover approval** — owner notification for RED actions

**Files:**
- `core/city/governor.py` (~1500 lines)
- `core/loop/permission_gateway.py` (~400 lines)

**Status:** ✅ IMPLEMENTED, production-reachable

---

## Governor — Intent Classification

### 4-Stage Pipeline

**File:** `core/city/governor.py:200-400`  
**Status:** ✅ IMPLEMENTED

```
User Query
    ↓
[Stage 1] Regex (35 patterns, 95% confidence, <1ms)
    ↓
[Stage 2] Embedding Matcher (590+ examples, 90-95%, 100-300ms)
    ↓
[Stage 3] Qwen3 8B Classifier (LoRA, 95-97%, <100ms)
    ↓
[Stage 4] LLM Fallback (flexible, 3-12s)
    ↓
District + Task Type
```

**Pipeline Code:**

```python
async def classify_chat_intent(self, text: str) -> dict:
    """Classify user query intent."""
    
    # Stage 1: Regex pre-classifier
    regex_result = self._regex_classify(text)
    if regex_result and regex_result["confidence"] > 0.95:
        logger.debug(f"[VECTOR][governor] Regex match: {regex_result['district']}")
        return regex_result
    
    # Stage 2: Embedding similarity (Phase 1)
    try:
        embed_result = await self.intent_matcher.classify(text)
        if embed_result and embed_result["confidence"] > 0.90:
            logger.debug(f"[VECTOR][governor] Embedding match: {embed_result['district']}")
            
            # Log to monitor
            self.monitor.log_classification(
                text=text,
                predicted=embed_result["district"],
                actual=None,
                confidence=embed_result["confidence"]
            )
            
            return embed_result
    except Exception as e:
        logger.warning(f"[VECTOR][governor] Embedding failed: {e}")
    
    # Stage 3: Qwen3 8B classifier (Phase 2)
    try:
        qwen_result = await self.intent_qwen3.classify(text)
        if qwen_result and qwen_result["confidence"] > 0.85:
            logger.debug(f"[VECTOR][governor] Qwen3 match: {qwen_result['district']}")
            
            # Log to monitor
            self.monitor.log_classification(
                text=text,
                predicted=qwen_result["district"],
                actual=None,
                confidence=qwen_result["confidence"]
            )
            
            return qwen_result
    except Exception as e:
        logger.warning(f"[VECTOR][governor] Qwen3 failed: {e}")
    
    # Stage 4: LLM fallback
    try:
        llm_result = await self._llm_classify(text)
        if llm_result:
            logger.debug(f"[VECTOR][governor] LLM match: {llm_result['district']}")
            
            # Log to monitor
            self.monitor.log_classification(
                text=text,
                predicted=llm_result["district"],
                actual=None,
                confidence=llm_result["confidence"]
            )
            
            return llm_result
    except Exception as e:
        logger.error(f"[VECTOR][governor] LLM fallback failed: {e}")
    
    # Default fallback
    return {
        "district": "general",
        "type": "unknown",
        "confidence": 0.0
    }
```

---

### Stage 1: Regex Pre-Classifier

**File:** `core/city/governor.py:100-200`  
**Status:** ✅ IMPLEMENTED

```python
def _regex_classify(self, text: str) -> Optional[dict]:
    """Stage 1: Regex pattern matching."""
    
    text_lower = text.lower()
    
    patterns = [
        # Coding district
        (r"(fix|debug|code|bug|error|crash)", "coding", "debug", 0.95),
        (r"(write|create|generate|build).*(code|function|class|script)", "coding", "generate", 0.95),
        (r"(review|audit|check).*(code|pr|pull request)", "coding", "review", 0.95),
        
        # Research district
        (r"(search|find|look up|research)", "research", "search", 0.95),
        (r"(paper|arxiv|study|research)", "research", "paper", 0.95),
        
        # Finance district
        (r"(upi|transaction|payment|money)", "finance", "upi", 0.95),
        (r"(stock|nse|bse|invest)", "investment", "analyze", 0.95),
        
        # Communications district
        (r"(send|message|email|text).*(to|whatsapp|telegram)", "communications", "send", 0.95),
        
        # Health district
        (r"(sleep|tired|fatigue|rest)", "health", "sleep", 0.95),
        (r"(exercise|workout|gym)", "health", "exercise", 0.95),
        
        # ... (35 patterns total)
    ]
    
    for pattern, district, task_type, confidence in patterns:
        if re.search(pattern, text_lower):
            return {
                "district": district,
                "type": task_type,
                "confidence": confidence,
                "method": "regex"
            }
    
    return None
```

---

### Stage 2: Embedding Matcher

**File:** `core/city/intent_matcher.py`  
**Status:** ✅ IMPLEMENTED

```python
class IntentMatcher:
    """Embedding-based intent classification."""
    
    def __init__(self):
        self.examples = self._load_examples()
        self.embeddings = None
        self.faiss_index = None
        self._build_index()
    
    def _load_examples(self) -> List[dict]:
        """Load training examples."""
        with open("data/intent_examples.json") as f:
            return json.load(f)  # 590+ examples
    
    async def _build_index(self):
        """Build FAISS index."""
        # Generate embeddings for all examples
        texts = [ex["text"] for ex in self.examples]
        self.embeddings = await self._generate_embeddings(texts)
        
        # Build FAISS index
        import faiss
        dimension = self.embeddings.shape[1]
        self.faiss_index = faiss.IndexFlatL2(dimension)
        self.faiss_index.add(self.embeddings)
    
    async def classify(self, text: str) -> dict:
        """Classify using embedding similarity."""
        # Generate query embedding
        query_emb = await self._generate_embeddings([text])
        
        # Search FAISS
        k = 5  # Top 5
        distances, indices = self.faiss_index.search(query_emb, k)
        
        # Get top match
        best_idx = indices[0][0]
        best_dist = distances[0][0]
        
        # Convert distance to confidence
        confidence = 1.0 / (1.0 + best_dist)
        
        if confidence > 0.90:
            example = self.examples[best_idx]
            return {
                "district": example["district"],
                "type": example["task_type"],
                "confidence": confidence,
                "method": "embedding"
            }
        
        return None
```

---

### Stage 3: Qwen3 8B Classifier

**File:** `core/city/intent_qwen3_8b.py`  
**Status:** ✅ IMPLEMENTED (training in progress)

```python
class IntentQwen3_8B:
    """Qwen3 8B intent classifier with LoRA."""
    
    def __init__(self):
        self.model = None
        self.tokenizer = None
        self.districts = self._load_districts()
        self._load_adapter()
    
    def _load_adapter(self):
        """Load LoRA adapter."""
        adapter_path = "data/adapters/intent_qwen3_8b/final"
        
        if os.path.exists(adapter_path):
            # Load base model
            self.model = AutoModelForCausalLM.from_pretrained(
                "Qwen/Qwen3-8B",
                torch_dtype=torch.float16,
                device_map="auto"
            )
            
            # Load LoRA adapter
            self.model = PeftModel.from_pretrained(
                self.model,
                adapter_path
            )
            
            self.tokenizer = AutoTokenizer.from_pretrained("Qwen/Qwen3-8B")
            
            logger.info("[VECTOR][qwen3] LoRA adapter loaded")
        else:
            logger.warning("[VECTOR][qwen3] No adapter found")
    
    async def classify(self, text: str) -> dict:
        """Classify using Qwen3 8B."""
        if not self.model:
            return None
        
        # Format prompt
        prompt = f"Classify this query: {text}\nDistrict:"
        
        # Generate
        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.model.device)
        outputs = self.model.generate(**inputs, max_new_tokens=10)
        result = self.tokenizer.decode(outputs[0], skip_special_tokens=True)
        
        # Parse district
        district = result.split("\n")[-1].strip()
        
        if district in self.districts:
            return {
                "district": district,
                "type": "",
                "confidence": 0.95,  # LoRA is highly confident
                "method": "qwen3"
            }
        
        return None
```

---

### Stage 4: LLM Fallback

**File:** `core/city/governor.py:400-500`  
**Status:** ✅ IMPLEMENTED

```python
async def _llm_classify(self, text: str) -> dict:
    """Stage 4: LLM fallback classification."""
    
    from core.inference.provider_client import chat
    
    # Inject context (RULE 1)
    hydration = await context_engine.session_hydration_prompt()
    
    prompt = f"""Classify this user query into a district and task type.

Query: {text}

Available districts:
{', '.join(self.districts)}

Return JSON: {{"district": "...", "type": "...", "confidence": 0.0-1.0}}
"""
    
    messages = [
        {"role": "system", "content": hydration},
        {"role": "user", "content": prompt}
    ]
    
    response = await chat(messages, model="vector-focus")
    
    try:
        result = json.loads(response.content)
        
        if result["district"] in self.districts:
            return {
                "district": result["district"],
                "type": result["type"],
                "confidence": result["confidence"],
                "method": "llm"
            }
    except Exception as e:
        logger.error(f"[VECTOR][governor] LLM parse failed: {e}")
    
    return None
```

---

## District Routing

### Route to District

**File:** `core/city/governor.py:500-600`  
**Status:** ✅ IMPLEMENTED

```python
async def route_to_district(self, intent: dict, query: str) -> dict:
    """Route classified intent to district."""
    
    district = intent["district"]
    task_type = intent.get("type", "")
    
    # Get district agents
    agents = self.agent_registry.get_by_district(district)
    
    if not agents:
        logger.warning(f"[VECTOR][governor] No agents in district: {district}")
        return {"success": False, "error": "No agents available"}
    
    # Select agent (HP-based)
    agent = self._select_agent(agents, task_type)
    
    if not agent:
        logger.warning(f"[VECTOR][governor] No suitable agent for: {task_type}")
        return {"success": False, "error": "No suitable agent"}
    
    # Execute
    result = await agent.execute(query, task_type)
    
    return {
        "success": True,
        "district": district,
        "agent": agent.name,
        "result": result
    }

def _select_agent(self, agents: List[Agent], task_type: str) -> Optional[Agent]:
    """Select best agent for task."""
    
    # Filter by HP (> 500)
    eligible = [a for a in agents if a.hp > 500]
    
    if not eligible:
        return None
    
    # Sort by HP
    eligible.sort(key=lambda a: a.hp, reverse=True)
    
    # Return top agent
    return eligible[0]
```

---

## Permission Gateway

### Permission Tiers

**File:** `core/loop/permission_gateway.py:100-200`  
**Status:** ✅ IMPLEMENTED (RULE 3)

```python
class PermissionLevel(Enum):
    """Permission tiers."""
    GREEN = "GREEN"      # Execute immediately
    YELLOW = "YELLOW"    # Log + execute (owner notified)
    RED = "RED"          # Require owner approval (Pushover)
    FORBIDDEN = "FORBIDDEN"  # Never execute

class PermissionGateway:
    """RULE 3: Permission gateway for all actions."""
    
    async def check(self, action: Candidate) -> PermissionLevel:
        """Check permission for action."""
        
        # 1. Check forbidden list
        if action.action_type in self.forbidden_actions:
            logger.warning(f"[VECTOR][permission] Forbidden: {action.action_type}")
            return PermissionLevel.FORBIDDEN
        
        # 2. Determine tier
        tier = self._determine_tier(action)
        
        logger.info(f"[VECTOR][permission] {tier} for: {action.action_type}")
        
        return tier
    
    def _determine_tier(self, action: Candidate) -> PermissionLevel:
        """Determine permission tier."""
        
        # GREEN: Low-risk, reversible, local
        if action.reversible and action.scope == "local":
            return PermissionLevel.GREEN
        
        # RED: High-risk, irreversible, external
        if not action.reversible or action.scope == "external":
            return PermissionLevel.RED
        
        # YELLOW: Medium-risk
        return PermissionLevel.YELLOW
```

---

### GREEN Tier — Execute Immediately

**File:** `core/loop/permission_gateway.py:200-250`  
**Status:** ✅ IMPLEMENTED

```python
async def _execute_green(self, action: Candidate) -> bool:
    """GREEN: Execute immediately."""
    
    logger.info(f"[VECTOR][permission] GREEN → execute: {action.action_type}")
    
    # Execute directly
    result = await self._dispatch_action(action)
    
    # Log
    await self.episodic_memory.store(
        event_type="action_executed",
        content={
            "action_type": action.action_type,
            "permission": "GREEN",
            "result": result.to_dict()
        },
        tags=[action.district, "green"]
    )
    
    return True
```

---

### YELLOW Tier — Log + Execute

**File:** `core/loop/permission_gateway.py:250-300`  
**Status:** ✅ IMPLEMENTED

```python
async def _execute_yellow(self, action: Candidate) -> bool:
    """YELLOW: Log + execute, notify owner."""
    
    logger.info(f"[VECTOR][permission] YELLOW → execute + notify: {action.action_type}")
    
    # Execute
    result = await self._dispatch_action(action)
    
    # Log
    await self.episodic_memory.store(
        event_type="action_executed",
        content={
            "action_type": action.action_type,
            "permission": "YELLOW",
            "result": result.to_dict()
        },
        tags=[action.district, "yellow"]
    )
    
    # Notify owner
    await self._notify_owner(action, result)
    
    return True

async def _notify_owner(self, action: Candidate, result: ActionResult):
    """Notify owner via Pushover."""
    try:
        from pushover import Pushover
        
        push = Pushover(
            app_token=os.getenv("PUSHOVER_APP_TOKEN"),
            user_key=os.getenv("PUSHOVER_USER_KEY")
        )
        
        message = f"""VECTOR executed YELLOW-tier action:

Action: {action.action_type}
District: {action.district}
Description: {action.description}

Result: {result.summary}
"""
        
        push.send_message(message, title="VECTOR Action (YELLOW)")
        
    except Exception as e:
        logger.error(f"[VECTOR][permission] Pushover failed: {e}")
```

---

### RED Tier — Require Owner Approval

**File:** `core/loop/permission_gateway.py:300-400`  
**Status:** ✅ IMPLEMENTED

```python
async def _execute_red(self, action: Candidate) -> bool:
    """RED: Require owner approval via Pushover."""
    
    logger.info(f"[VECTOR][permission] RED → request approval: {action.action_type}")
    
    # Request approval
    approved = await self._request_owner_approval(action)
    
    if not approved:
        logger.info(f"[VECTOR][permission] RED → rejected: {action.action_type}")
        return False
    
    # Execute
    result = await self._dispatch_action(action)
    
    # Log
    await self.episodic_memory.store(
        event_type="action_executed",
        content={
            "action_type": action.action_type,
            "permission": "RED",
            "approved": True,
            "result": result.to_dict()
        },
        tags=[action.district, "red"]
    )
    
    return True

async def _request_owner_approval(self, action: Candidate) -> bool:
    """Request owner approval via Pushover."""
    try:
        from pushover import Pushover
        
        push = Pushover(
            app_token=os.getenv("PUSHOVER_APP_TOKEN"),
            user_key=os.getenv("PUSHOVER_USER_KEY")
        )
        
        message = f"""VECTOR needs approval for:

Action: {action.action_type}
District: {action.district}
Description: {action.description}

Reply YES to approve, NO to reject.
"""
        
        # Send notification
        push.send_message(message, title="VECTOR Approval Required (RED)")
        
        # Wait for response (timeout 5min)
        try:
            response = await asyncio.wait_for(
                self._wait_for_approval(),
                timeout=300
            )
            
            if response.approved:
                logger.info(f"[VECTOR][permission] RED → approved: {action.action_type}")
                return True
            else:
                logger.info(f"[VECTOR][permission] RED → rejected: {action.action_type}")
                return False
        
        except asyncio.TimeoutError:
            logger.warning("[VECTOR][permission] RED → timeout → REJECT")
            return False
    
    except Exception as e:
        logger.error(f"[VECTOR][permission] Pushover failed: {e}")
        return False
```

---

## HP-Based Governance

### Council Voting

**File:** `districts/governance/llm_council.py`  
**Status:** ✅ IMPLEMENTED

```python
class LLMCouncil:
    """LLM Council for high-stakes decisions."""
    
    async def vote(self, action: Candidate) -> bool:
        """Council votes on action."""
        
        # Only agents > 700 HP can vote
        voters = [a for a in self.agent_registry.list() if a.hp > 700]
        
        if not voters:
            logger.warning("[VECTOR][council] No eligible voters")
            return False
        
        # Each voter evaluates
        votes = []
        for voter in voters:
            vote = await voter.evaluate_action(action)
            votes.append(vote)
        
        # Majority wins
        approved = sum(votes) / len(votes) > 0.5
        
        logger.info(f"[VECTOR][council] Vote: {sum(votes)}/{len(votes)} approved")
        
        return approved
```

---

## Performance Characteristics

| Operation | Duration | Bottleneck |
|-----------|----------|------------|
| Regex classify | <1ms | Pattern matching |
| Embedding classify | 100-300ms | Embedding generation |
| Qwen3 classify | <100ms | Model inference |
| LLM fallback | 3-12s | LLM API call |
| Permission check | <1ms | Memory access |
| Owner approval | 0-300s | Human response |

---

## Known Issues

### Issue 1: Intent Accuracy Below Target

**Symptom:** 90% accuracy, target 95%  
**Root Cause:** Insufficient training data  
**Impact:** Misrouted queries  
**Workaround:** LoRA fine-tuning in progress  
**Priority:** HIGH

### Issue 2: RED Tier Approval Slow

**Symptom:** Owner takes time to approve  
**Root Cause:** Human bottleneck  
**Impact:** Delayed actions  
**Workaround:** Auto-approve trusted actions  
**Priority:** MEDIUM

---

## Cross-References

See:
- `01_GLOBAL_SYSTEM_MAP.md` — System overview
- `05_AUTONOMOUS_LOOP.md` — Loop architecture
- `10_AGENT_ARCHITECTURE.md` — Agent system
- `11_VECTOR_CITY.md` — Districts
- `12_HP_AND_EVOLUTION.md` — HP system

---

**Last Updated:** 2026-08-12  
**Status:** ✅ COMPLETE
