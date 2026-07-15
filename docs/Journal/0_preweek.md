# Preweek Technical Documentation

## Technical Goal
The technical goal of Preweek (Explore) is to determine how well do Agent Architectures fit our business use-case.

[Ref 1] Examples of Agent Architectures That Scale with Effort:
- An agent file with referenced files eg. AGENT.md. @~/docs/*.MD
- Agent Skills driven by main agent eg. ~/skills
- Filesystem Subagent driven by a coding harness or Coding Agent SDK eg. ~/subagents
- AI workflow automation platform eg. n8n
- Use generic AI Agent SDK that leverages plug and play generic AI packages
- Use low level first-party LLM SDKs and write our own agentic loop
- Use REST APIs directly, write our own agentic loop
  - The agentic loop is model-driven orchestration with middleware programmatic guidance
  - The agentic loop is code-driven orchestration

## Technical Uncertainty
- I'm uncertain if a coding harnesses agentic loop is effective/productive enough to drive a non-codng workload.
- I'm uncertain if LLMs model's thinking mode and other intelligent parameters is sufficent enough to hold memory and drive decisions for work specific use-cases.
- I'm uncertain that a coding harness can ineract with a MUD without an interface or SDK or manage the telnet session.

## Technical Hypotheses
- Based on our [Ref 1] I think that we will have issues with the coding harness driving the MUD without an interface because we don't use a defined API, we are driving commands over a protocol that we need to live-monitor.  Telnet communication seems like it would be a sticking point
- I think we will need an interface because managing a long-lived telnet session may prove difficult.  In the past I've always found managing live-sessions challenging.

- I think that the only agent architecture that will be able to drive our use-case will be where we implement a specialized agentic loop, as I think generic model memory will not be capable enough to remember and navigate the MUD world.

- I think that we need to roll-our-own agent without an SDK because generic primitives for observability, for mrrmory, and our use-case will require specialized implementation.  And that we want to connect broadly with all frontier models and many SDKs will lack one of them.


## Technical Observations
- An Agent.md could not connect to the MUD, it could produce scripts but it was unreliable in creating a connection to the MUD and needed knowledge of the deterministic TUI of the MUD.
- Skills and Subagents performed accompanied with a script to manage the telnet session.  They were able to play the MUD, but maybe not efficiently.
- Using Markdown files where the coding harness updates simple memory files produced brittle navigation instructions. eg.:

```sh
To reach the **Newbie Zone** from Market Square:
1. `north` -> Temple Square
2. `north` -> Temple
3. `north` -> Altar
4. `north` -> Behind Altar
5. `north` -> Great Field
6. `north` -> Great Field (with newbie zone sign)
7. `east` -> Newbie Zone entrance
8. `north` -> Enter corridor
```

## Technical Conclusions
- Skills and Subagents are capable of drivng the MUD.  
- We do need specialized memory for map navigation and world data
- We opened a new technical use-case of if we should have our agent handle multiple sessions of multiplayers, playing at the same time since co-op is a common factor in MUDs which we forget to consider in our design.
- We could not explore n8n completely due to technical restraints executing external scripts.
- Implementing our specialized loops remain technical uncertain and will need to be explored in depth in Week 2.
- Without a customized agentic loop the agents could not perform goals efficently.  And did not have any key meta strategies or journey player strategies.

## Key Takeaway
When we have a specialized use-case like playing a MUD, we likely cannot leverage generic SDKs for Agents because we need specialized tooling and agentic loops.
