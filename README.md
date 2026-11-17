# Herald

https://github.com/aleyu0/herald


Herald is a multi-user event discovery platform for UCSD. Users can upload or take a picture of event flyers, which gets sent to an LLM to extract the structured information, and the event can be saved as public or private. Public events are shown on all user's feeds while private events are only seen on the uploaded user's feed. Event detail pages have stable URLs for sharing and an .ics download link for adding to any calendar app. 

## How it works

The frontend is built with Next.js and deployed on Vercel. The backend is a FastAPI server running on a DigitalOcean droplet behind Nginx. Supabase handles the database, authentication, and image storage.

The flyer scanning pipeline runs a multi-stage deduplication check. The uploaded image is first checked using pHash to see if it is an identical or near-identical image to an existing event. If it passes, the LLM extracts the event fields and returns a structured result for the user to review. When the user presses save, a second check runs against other public events on the same date using weighted fuzzy scoring on title, organizer, and location similarity. A separate lightweight LLM call classifies the event into one or more tags from a fixed set.

User corrections are stored in the corrections table when a user edits the extracted fields before saving. Rather than injecting all corrections into every future scan, they are periodically summarized into a correction_summaries table by a separate LLM call. This keeps the prompt size bounded as corrections scale.

Auth is handled by Supabase. The backend uses the service role key for all writes, which bypasses row-level security but requires an explicit user_id on every insert. The browser uses the anon key so that unauthenticated users cannot access private events. When the backend receives a request, it checks the user's token by asking Supabase directly through `supabase.auth.get_user(token)` so that it keeps the backend decoupled from whatever signing algorithm Supabase uses internally.

The feed supports tag filtering via chips at the top, a debounced search bar for finding events by title, organizer, or description, and a Following section that surfaces events from organizers and tags the user has followed. Users can star events to mark them as interested, which populates a dedicated /interested page. Event owners can edit their events from the detail page. Events can also be added manually without a flyer through a form on the upload page.

## Eval and test data

There is no automated eval harness for Herald. The deduplication pipeline was tested component by component against a fixed dataset built around a single UCSD event flyer: a clean screenshot, a cropped version of the same screenshot, a straight-on photograph of the flyer, and a photograph taken at an angle. This dataset was used to determine what each pre-extraction method could and couldn't handle reliably.

See `DESIGN.md` for more details on the evaluation.

