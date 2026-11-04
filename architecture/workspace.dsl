/*
 * Permit Engine: C4 model as code (Structurizr DSL). It describes what exists for the 2026-11-04 demo.
 * Public wording: the LLM is called "agentic LLM", and no vendor or model is named here or in the export.
 *
 * Validate and export with the local image, from the repository root:
 *   docker run --rm --pull=never -v "$PWD/architecture":/w structurizr/structurizr validate -w /w/workspace.dsl
 *   docker run --rm --pull=never -v "$PWD/architecture":/w structurizr/structurizr export -w /w/workspace.dsl -f json -o /w/export
 *
 * How the levels are used:
 *   Level 1, system context: view "Context"
 *   Level 2, containers: view "Containers". A container is something that runs or holds data on its own.
 *   Level 3, components: view "Components". The parts inside the Engine container.
 *   Flows: the dynamic views ReadApplication, DecideCase, ReviewAndLearn, ReleaseChange and PublishAndCheck.
 *   Each step's description is "Title: what happens", and the site splits it at the first colon.
 *   How the system was tested is the separate Test bench system, drawn only on the Testing page (view "TestBench").
 *
 * gov_design/site/build.mjs reads export/workspace.json and draws these views. Box positions are in
 * gov_design/site/lib/architecture.tsx, so a new element in a view needs a position there or the build stops.
 *
 * Relationships are written by hand at each level, so implied relationships are off.
 */
workspace "Permit Engine" "A decision system for public-event permits, shown on synthetic street-race applications. An agentic LLM reads the evidence, Jev answers narrow questions, code does the arithmetic, Rego decides, and an officer settles the rest." {

    !impliedRelationships false

    model {
        applicant = person "Applicant" "Sends a form, a cover letter and attachments. In this demo a script writes them." "Stand-in"
        officer = person "Officer" "Rules on cases the decision table sends to an officer. In this demo an LLM stands in." "Stand-in"
        policyOwner = person "Policy owner" "Owns the trees, thresholds and settings, and releases new versions."
        steward = person "Steward" "Owns the evidence map: which documents count as proof of what."
        visitor = person "Visitor" "Opens any decision in the replay and reads how it was reached. Changes nothing."

        llm = softwareSystem "Agentic LLM" "A hosted language model. Reads documents in two fixed passes with no tools. It never decides." "External"
        jev = softwareSystem "Jev" "A TypeSafe model with fixed weights. Answers narrow questions as probabilities." "External"
        site = softwareSystem "Architecture site" "Static pages at the address on the printed poster. Built from this model and the report files." "External"
        tunnel = softwareSystem "Cloudflare tunnel" "A named tunnel to one public hostname. The only way in from outside." "External"

        engine = softwareSystem "Permit Engine" "Reads an application, assesses risk with trees that can learn, and decides by written rules. Every decision can be retraced." {
            applications = container "Applications" "The form, cover letter and attachments of each case." "Files" "Store"
            rules = container "Rule files" "The ordinance, evidence map, trees, Rego and settings. Changing a value needs no code change." "YAML, JSON, Rego" "Store"
            core = container "Engine" "The program that reads, decides, learns and publishes. It holds no policy values." "Python, command line" {
                reader = component "Reader" "Runs the reading stages once per case and stores the answers." "Python"
                checks = component "Code checks" "The quote check and the field comparison. Plain code with no policy values." "Python"
                pipeline = component "Case pipeline" "Turns a stored record, weights and thresholds into a decision. A pure function of its inputs." "Python"
                arithmetic = component "Tree arithmetic" "Sends a case down each tree and gives likelihood, severity, the risk sum and the highest severity." "Python"
                builder = component "Run builder" "Takes cases in order, decides each, asks for a review, teaches the trees and writes the log." "Python"
                officerDesk = component "Officer desk" "Hands a case to the officer and brings back the ruling." "Python"
                learning = component "Learning" "Applies a review to leaf counts, fits candidates, chooses thresholds and releases versions." "Python"
                exporter = component "Exporter" "Writes a finished run as JSON, and scans every file for vendor names and keys first." "Python"
                reproduce = component "Reproduce" "Reruns a logged decision with no model calls, and refuses if what it used has changed." "Python"
            }
            opa = container "OPA" "Runs the Rego policies, with no network, time or random functions." "Open Policy Agent, subprocess"
            stored = container "Stored answers" "One reading record per case, and every model call keyed by a hash of its input." "JSON files" "Store"
            weights = container "Weights and versions" "Candidate and released weights with their thresholds. Released versions never change in place." "JSON files" "Store"
            log = container "Event log" "One file per run. Triggers reject updates and deletes. Holds the hashes of what each decision used." "SQLite" "Store"
            run = container "Exported run" "One finished run as a folder of static files." "JSON" "Store"
            server = container "File server" "Serves that one folder from 127.0.0.1. Holds no keys and has no model client." "Python http.server"
            replay = container "Browser replay" "Plays the finished run in each visitor's browser. No action buttons." "React, Vite"
        }

        bench = softwareSystem "Test bench" "Makes the synthetic cases and scores the engine against them. It plays no part in how a case is decided." {
            generator = container "Synthetic data generator" "Writes every application, its hidden facts and its labels from one seed." "Python"
            cards = container "Case cards" "The hidden facts of each case. Never read by the models or the pipeline." "JSON Lines" "Store"
            labels = container "Labels" "Risk levels, risky or not, and the right route, set by a hidden truth table." "JSON Lines" "Store"
            rubric = container "Expert rubric" "The truth table in plain words. Only the simulated officer reads it." "Markdown" "Store"
            standIn = container "Simulated officer" "An LLM following the expert rubric, standing in for a person. No tools. Always labelled as simulated." "Python"
            evaluation = container "Evaluation" "Runs each arm, the sealed test and the tone test, and scores them." "Python"
            results = container "Reports and ledger" "The reports, the spend meter and the ledger that lets the sealed test run once." "JSON, Markdown" "Store"
        }

        # Level 1: the system and what surrounds it.
        applicant -> engine "Submits a form, a cover letter and attachments"
        engine -> officer "Sends cases to rule on, and gets back a ruling, a reason and risk levels"
        policyOwner -> engine "Sets the trees and settings, and releases new versions"
        steward -> engine "Keeps the evidence map"
        visitor -> engine "Opens any decision and reads how it was reached"
        engine -> llm "Sends documents, and gets back fields with quotes and verdicts"
        engine -> jev "Sends typed values and plans, and gets back probabilities"

        # Level 2: what runs and what holds data.
        applicant -> applications "Sends"
        steward -> rules "Edits the evidence map"
        policyOwner -> rules "Edits trees and settings"
        policyOwner -> core "Runs train, thresholds and release"
        core -> applications "Reads"
        core -> rules "Reads"
        core -> opa "Runs as a subprocess"
        opa -> rules "Loads Rego"
        core -> stored "Writes and reads one record per case"
        core -> weights "Reads and writes"
        core -> log "Writes every stage as an event"
        core -> run "Writes the finished run"
        core -> llm "Sends two fixed passes"
        core -> jev "Sends one request per case"
        core -> officer "Asks for a ruling"
        server -> run "Serves"
        replay -> server "Loads the page and JSON"
        visitor -> replay "Watches, and opens any case"

        # Level 3: inside the Engine container.
        reader -> applications "Loads the form, letter and attachments"
        reader -> rules "Reads the kinds of proof and the questions"
        reader -> opa "Asks for basic checks and the hazard screen"
        reader -> llm "Sends the two fixed passes"
        reader -> checks "Checks quotes"
        reader -> jev "Sends one request"
        reader -> stored "Writes one reading record"
        builder -> pipeline "Decides each case with the weights of the moment"
        pipeline -> stored "Reads the record"
        pipeline -> checks "Compares fields with the form"
        pipeline -> opa "Asks for statuses, rule answers and the decision"
        pipeline -> arithmetic "Asks for likelihood, severity and risk"
        builder -> officerDesk "Asks for a review"
        officerDesk -> officer "Hands over the case"
        builder -> learning "Applies each review and re-chooses thresholds"
        builder -> log "Writes every stage as an event"
        policyOwner -> learning "Runs train, thresholds and release"
        policyOwner -> weights "Reads the validation result"
        learning -> stored "Reads, with no model calls"
        learning -> weights "Writes candidates and released versions"
        exporter -> log "Reads the finished run"
        exporter -> run "Writes static JSON"
        reproduce -> log "Reads a logged decision"
        reproduce -> pipeline "Reruns it with no model calls"

        # The test bench. Drawn only on the Testing page.
        generator -> applications "Writes forms, letters and attachments"
        generator -> cards "Writes the hidden facts"
        generator -> labels "Writes levels, risky or not, and the right route"
        core -> labels "Fits weights and re-chooses thresholds from labelled cases"
        core -> standIn "Asks for a ruling, in this demo"
        standIn -> rubric "Reads"
        standIn -> llm "Sends one call with no tools"
        evaluation -> core "Runs each arm through the pipeline"
        evaluation -> labels "Scores against"
        evaluation -> cards "Checks readings against"
        evaluation -> results "Writes"
        evaluation -> llm "Asks directly, as the baseline"
        evaluation -> jev "Asks directly, for comparison"

        # Where it runs.
        tunnel -> server "Forwards reads to"
        visitor -> tunnel "Opens the replay through"
        visitor -> site "Reads"
        site -> tunnel "Links to"

        demo = deploymentEnvironment "Demo" {
            deploymentNode "Project owner's Mac" "Cases are read, decided and ruled here, ahead of time." "macOS" {
                containerInstance core
                containerInstance opa
                containerInstance applications
                containerInstance rules
                containerInstance stored
                containerInstance weights
                containerInstance log
                containerInstance run
                containerInstance server
            }
            deploymentNode "Model providers" "Called from the Mac, ahead of time only. Visitors never reach them." "Hosted APIs" {
                softwareSystemInstance llm
                softwareSystemInstance jev
            }
            deploymentNode "Cloudflare" "Sends reads from one public hostname to the file server." "Named tunnel" {
                softwareSystemInstance tunnel
            }
            deploymentNode "Visitor's device" "Plays the run from static files. No model call and no key." "A web browser" {
                containerInstance replay
            }
            deploymentNode "GitHub Pages" "This site, at the address on the printed poster." "Static pages" {
                softwareSystemInstance site
            }
        }
    }

    views {
        systemContext engine "Context" "Level 1. Permit Engine, who uses it, and the two models it calls." {
            include engine applicant officer policyOwner steward visitor llm jev
            autoLayout lr
        }

        container engine "Containers" "Level 2. What runs and what holds data inside Permit Engine." {
            include applicant officer policyOwner steward visitor llm jev
            include applications rules core opa stored weights log run server replay
            autoLayout lr
        }

        component core "Components" "Level 3. The parts inside the Engine, and what each one uses." {
            include reader checks pipeline arithmetic builder officerDesk learning exporter reproduce
            include applications rules opa stored weights log run llm jev officer policyOwner
            autoLayout lr
        }

        dynamic core "ReadApplication" "Reading one application. It runs once per case, and the answers are stored." {
            reader -> applications "Open the application: The Reader loads the form, the cover letter and the attachments of one case."
            reader -> opa "Basic checks: Is the fee paid, is the form complete, is the date allowed? A failure stops the case here, before any model is called."
            reader -> llm "Link and extract: In the first pass, for each kind of proof a race can need, the LLM says found or absent, gives fields with quotes, and lists documents that fit no kind. This is the only pass that reads the cover letter."
            reader -> checks "Quote check: Each quote must appear in the named attachment and each value inside its quote, or the field counts as absent. The form and the cover letter are never allowed as sources, so a letter cannot become evidence."
            reader -> llm "Judge: In the second pass, in a fresh context, the LLM gets the attachments behind verified fields and the case's typed values, never the cover letter. It gives one verdict per kind of proof: supported, unsupported or contradicted."
            reader -> opa "Hazard screen: By rules only, traffic applies if a road closes, crowd pressure if the crowd is 300 or more, and medical always."
            reader -> jev "Tree questions: One Jev request per case, with typed values, evidence records and whole plan documents. Jev returns a probability for each question on the hazards that apply. It never sees the cover letter."
            reader -> stored "Store the answers: All of this becomes one reading record. From here on, the case needs no model call."
            autoLayout lr
        }

        dynamic core "DecideCase" "Deciding one case. No model is called, so any decision can be reproduced." {
            builder -> pipeline "Pick up the case: The Run builder hands the case to the pipeline, with the weights and thresholds of the moment."
            pipeline -> stored "Load the reading record: The pipeline starts from the stored answers, not from a new model call."
            pipeline -> checks "Compare fields with the form: Code compares each extracted field with the form. A mismatch, such as a letter naming another date, makes the record contradicted whatever the LLM said."
            pipeline -> opa "Requirements and rule answers: Rego gives each requirement a status (met, failed, missing or unclear), and answers every question the form can settle."
            pipeline -> arithmetic "Work out the risk: Answers send the case down up to six trees. Each hazard's likelihood times its severity, summed over the hazards that apply, gives the risk."
            pipeline -> opa "Apply the decision table: Rego reads the table from the top, and the first match wins: returned, proposed denial, officer or approved, with the row, the reason and the clause."
            builder -> log "Log the decision: Every stage is written as an event, with the hashes of everything the decision used. If the write fails, the decision does not take effect."
            autoLayout lr
        }

        dynamic core "ReviewAndLearn" "An officer reviews a case, and the trees learn from it." {
            builder -> officerDesk "Send it to review: Every case except a returned form goes on. A case sent to an officer gets a ruling, and any other case gets a review of what the system did."
            officerDesk -> officer "The officer rules: The officer sees the documents, the decision, the risk and the trees to give a level for. They return a ruling, risky or not, a one-line reason and a level per tree. A real deployment would use a person. In this demo an LLM stands in, always labelled as simulated."
            builder -> log "Log the ruling: The ruling is logged with who made it. A permit is only issued with a logged decision or ruling as its parent."
            builder -> learning "Teach the trees: Every review teaches, not only disagreements. A Bayesian network works back from the outcome and the named levels, and adds shares to the counts on the leaves this case reached, after discounting their old counts."
            builder -> log "Log the new weights: The new weights version is logged. If the review disagreed with the system's estimate, it is also logged as a correction, with old and new values."
            builder -> learning "Re-choose the thresholds: At a set interval of reviews, the two thresholds are chosen again, because thresholds fitted to one set of weights do not fit the next."
            builder -> pipeline "Decide the next case: Later cases use the new weights and thresholds, and each records the version it used."
            autoLayout lr
        }

        dynamic core "ReleaseChange" "A person makes a change official." {
            policyOwner -> rules "Edit a rule file: A change is data, not code: a tree question, a setting or a first guess. A lint command checks the rule files, and a setting outside its limits stops the run."
            policyOwner -> learning "Fit a candidate: The policy owner runs train and thresholds. Models are not called again."
            learning -> stored "Read the stored answers: Fitting reads the answers already stored for each case, so it makes no model call."
            learning -> weights "Write the candidate: Candidate weights and thresholds are written beside the released ones. Nothing uses them yet."
            policyOwner -> weights "Read the result: The policy owner reads the candidate's validation result, and either releases it or leaves it."
            policyOwner -> learning "Release: The policy owner runs release under a new version name."
            learning -> weights "Keep every version: Release copies the candidate to the new version, with the role and the hashes it was fitted on. Released versions never change in place, and it refuses to overwrite one."
            autoLayout lr
        }

        dynamic core "PublishAndCheck" "A finished run reaches a visitor, and any decision in it can be checked." {
            exporter -> log "Read the finished run: The Exporter reads the log of one finished run."
            exporter -> run "Write static files: It writes the run as JSON and scans every file for vendor names and keys. Only then does it replace the old folder."
            server -> run "Serve one folder: A plain file server sends that folder. It holds no keys and runs no application code."
            visitor -> replay "Open the page: Any visitor can open the replay and any case, with no login. There are no action buttons."
            replay -> server "Play the run: The browser loads the JSON and plays the run. Nothing is computed for the visitor, and no model is called."
            reproduce -> log "Pick a decision to check: The replay command reads a logged decision and the hashes of what it used."
            reproduce -> pipeline "Run it again: It reruns the decision with no model calls and checks that the result is identical. It refuses if the rules, the settings, the application or the arithmetic have changed."
            autoLayout lr
        }

        container bench "TestBench" "How the test bench wraps the engine. It writes the cases, holds the labels and scores the results." {
            include generator cards labels rubric standIn evaluation results applications core llm jev
            autoLayout lr
        }

        deployment engine "Demo" "Deployment" "Where each part runs during the demo." {
            include *
            autoLayout lr
        }

        styles {
            element "Person" {
                shape person
                background #0f2a4a
                color #ffffff
            }
            element "Stand-in" {
                border dashed
            }
            element "Container" {
                background #0f2a4a
                color #ffffff
            }
            element "Component" {
                background #eaf1f9
                color #0f2a4a
            }
            element "Store" {
                shape cylinder
                background #eaf1f9
                color #0f2a4a
            }
            element "External" {
                background #ffffff
                color #0f2a4a
                border dashed
            }
        }
    }
}
