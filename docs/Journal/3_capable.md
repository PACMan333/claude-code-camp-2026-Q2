# Week 3 Technical Documentation


## Technical Goal
The technical goal in this week of the bootcamp is to get the Agent to be able to find the bakery in the least amouint of moves.

## Technical Uncertainty
Can we get less token use from the MUD Agent to Claude?  Can we find the Bakery in less steps?

## Technical Hypotheses 
I think with settting up a smaller payload in the API calls to claude by limiting the command payload will use less tokens, creating a BFS linked db of all the rooms that the MUD Agent can find will help make it easier for the Agent to find locations in the MUD and save in token use.

## Technical Observerations
Updated the settings.yaml file to include all the tools that I want Claude to use with a yes/no keyword, this now just sends 3 commands, not all 55, in eaxh API call packet now.  This will use less API tokens on each API call now.  You can see this change by the MUD(#) that lits tot tools loaded now:

![BK Tools list screen shot](image-8.png)

## Technical Conclusions
Reflecting back your education guesses from the technical uncertainty section what was the technical outcomes. Is there any new technical uncertainty that has been put aside for future exploration. Are there any next steps or technical considerations worth noting?


## Key Takeaway
In one sentence. State the most important lesson from the week.