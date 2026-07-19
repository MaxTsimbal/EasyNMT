# Easy Tutor Brain

This release adds a lightweight local layer between the learner and OpenAI.

Flow:

`user request -> local intent analysis -> adaptive tutor instructions -> OpenAI Responses API -> Easy answer`

The analyzer recognizes:
- explain from zero;
- solve a task;
- check an answer or photo;
- practice with hints;
- concise recap;
- confusion;
- repeated failed explanation.

It does not make an extra API call, so understanding the request does not double token cost or latency.
