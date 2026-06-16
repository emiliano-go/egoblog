---
title: The Way I Study
---

Studying, the art of **learning**, and, for me, an amazing experience.

I've always considered me a **Filomath**, as I've been curious about everything and anything for as long as I can remember.

When I was **younger**, I was really into **Astronomy**. My grandfather was (and is) an amateur astronomer, and studied astronomy for years in college, even tough he was a doctor. I've learned a lot of what I know about astronomy from him, but I've also studied it on my own. Did you know that, hypothetically, we could all vanish in about 8 minutes if even a **tiny spec** of rare matter collided with earth? Fun, right?

Anyway, as I grew up, different topics attracted my interest: immunology, psychology, web development (as a whole), and then, as of this year, data science. Having these interests (and a strict studying regime) allowed me to develop a specific way of studying as to maximize my learning.

My learning workflow is separated in **two** big steps: **Absorbing** and **Applying**.

There are some differences on how I learn different topics, but I've got a good enough generalization, which I'll use from now on, to separate topics in three categories:
- **Mathematics**, be it Linear Algebra, Calculus or Statistics, but specifically, the practical aspect, not much the theory
- **Software Engineering**, enclosing everything from APIs to Data Structures, both for backend and infrastructure, etc.
- **Theoretical Courses**, those being heavy **text-based topics**, like immunology, psychology, statistical theory, business logic, etc.

I'll specify which study method or technique I use each of those groups.

## Absorbing

Absorbing knowledge is easy, it's **retaining** knowledge what is actually hard. To absorb information, you usually only got to spam the shit out of a topic until you understand it enough as to start applying it by yourself.

For **Mathematics**, I often take a book about the topic I want to learn and do all the exercises available while going through the book. For simple topics I don't really take notes, unless there's some super specific rule or concept I need to continue. On the other hand, for complex topics I typically take notes, write demonstrations and sometimes even add a practical example, if it's difficult enough. Most of the time I just read and do exercises for 1-2hs. If there's something I don't understand, I use DeepSeek or Claude for a quick explanation. Most math problems are methodical after the 20ht exercise, so it's important to mechanize the process while understanding **why** that mechanism works.

For **Software Engineering**, reading documentations beats almost everything else. For overviews, I watch videos like [Luke Barousse's Data Engineer overview](https://www.youtube.com/watch?v=_-DzZeixu0w) or [Tech with Tim's Data Structures video](https://www.youtube.com/watch?v=J2fol8eWo64), which allow me see the bigger picture and find what I want or need to learn. But to learn something, nothing is better than raw documentation. FastAPI documentation is, by far, one of the best ones I've read, but Django's and Fastify's are also very good. Documentation is good to understand syntax, code structure, inner workings and patterns, but falls short if not properly implemented. Also, you can't code on the bus, but you can almost always read. Although, for more complex and in-depth implementations, like **Data Structures** or **Patterns**, a book always wins. Not because documentation is not good enough, but because documentation is **technical**, while **books are human**. What I mean by this is that documentation expects an experienced reader that is revisiting the topic, while books (and their authors) introduce the topic from a more **approachable** perspective, usually with IRL examples and easier language.

For **Theoretical Courses**, books books books. Even though they're heavy to process, long and extensive books allow for a better understanding of topics like psychology, because they have the length to get through complex topics, like human behavior or innate immune response. Be aware, learning pure theory is a Sisyphean task, but that's why choosing the right book is very, very important. For immunology, as an introduction, I always recommend Philip Dettmer's “Immune” book, and just then start reading proper medical books. The same applies for statistics, psychology, etc. What I've found especially useful is to join forums and ask for book recommendations (and, as always, wait for people to stop killing themselves before reading), be it through Discord, Reddit, or even local forums.

Now, as a general note, I always take notes, independently of what I'm learning. Notes don't have to be very extensive nor exact, but must instead focus on critical concepts, flows, ideas, that allow to expand on the topic when cleaning the notes. Yes, I clean my notes. I take my bazillion pages of gibberish Samsung Notes and then take my time “translating” everything into something **useful to come back to**, so I have grounds to come back to if I ever get lost. For that, I use obsidian, on a [public vault](https://equinox.emiliano-gandini-outeda.uy/) you can check, though, be aware, it's not meant to be pretty, but useful.

## Applying

Applying knowledge doesn't mean doing set exercises or guided demonstrations. Applying knowledge means to take whatever you know and dump it to solve an esoteric problem you made up exclusively to apply said knowledge. This obviously isn't very easy to implement in practice, but it can be done if you're creative enough. Obviously it's easier to apply things related to **Software Engineering** or **Statistics**, but I've found that, through code, almost everything can be represented.

### Fucking Around to Find Out

To **Find Out** what problems I can solve, the best way I've found is **fucking around**, both IRL and in forums, with people.  Why? Social interactions allow you to discover new things to solve or something related that evolves into a well-defined issue to attack. Most of the bigger practical applications I've made come from solving other people's concerns, be it a complex angle calculator or a full-fledged CRUD application for storing recipes, both of which I used as practical application of concepts.

Even if you can't get a detailed objective of what you can do, start small: create a small and perfect script that solves the aspect you understood of the problem, and then expand it be both abstract and general, allowing, in the end, the creation of a complete system probably no one will use, but that will demonstrate to yourself (and your possible employer) that you know X or Y things.

### Make, Break, Fix, Expand, Repeat

"Make, Break, Fix, Expand, Repeat" represents the central motto of my studying method, independently of the topic. It can be easily applied to most projects and is probably the best approach I've found. This approach obviously depends on having a somewhat defined objective with some kind of closed scope (as to avoid big generalization), so this is the step after **finding out**.

#### Make

You start writing code. Yes, code. Oh, you studied math? Don't care, code. Same for immunology, statistics, software engineering (duh) and anything else you find. If it exists, it means it can be conceptualized and therefore written as code, be it a math formula, human behavioral patterns or interferon propagation.

For **mathematics**, you need a use case for the formula. Then, write the formula from scratch, no libraries, and use it as is, even if it's not efficient. Same for any algorithm you need to implement for **software engineering**. For theoretical topics, things become harder: you need to create a full representation of the situation (e.g., an interferon propagation simulator) to correctly represent the topic,

#### Break

Because I made things fast and dirty, that means they're gonna break, and I want them to break. The same way falling is part of learning to walk, breaking is part of learning to **create**. Everything you have created and will create has or will eventually break. This is expected, as nothing lasts forever, and that's why you require things to break during your “training”, because that allows you to understand:
- **What** broke
- **Where** it broke
- **How** it broke
- **Why** it broke.

**What** broke identifies what part of the complex system you **made** before broke. That can be a math formula giving a wrong result, an edge case causing a memory leak, an over-fitted model, etc. Knowing how to identify the culprit is hard, and that why things need to brake early. The bigger the tower, the bigger the fall.

**Where** it broke is the abstraction layer and specific location (line, function, pipeline stage or data slice) where the failure manifests.

**How** it broke represents the sequence of operations and state changes leading from correct preconditions to the failure itself.

**Why** it broke **is**, most of the time, the **debugging**. It **is** the break point, which usually is pretty much the same everywhere: mishandled edge case, recursive functions, wrong features selected, etc. These require good knowledge of the topic you're dealing with, but also good understanding of what the code does (that's why you don't use AI) so logic debugging is easier.

#### Fix

With all that knowledge about the issue I now know, I start fixing. First, the good old `print` debugging never fails to get rid of 90% of the errors I found. 

Then, the funny step begins: **logical debugging**. This is, by far, the best and worse part of fixing. The best because it's the one when you really learn how to properly build a system, as you learn proper debugging and better coding techniques, and the worse because it's the hardest kind of debugging. Logical debugging means finding the error on **your own thoughts, translated to code**. So you need to translate **back** the code to thoughts and then think again "Why did this fail?". That's why I don't write code with AI, translating code I didn't write into thoughts is very, very hard. Fixing is a very important step in learning, as it allows you to apply new concepts, be it as patches, reworks, refactors or straight up a completely new approach.

#### Expand

Expanding means to give 105%, to go a step further, to take a risk. "Nothing changes if nothing changes" kinda vibe. You always want to make that weird feature, to try to optimize that function, to write that blog. This is where you **grow**. But be aware, "Grow for the sake of grow is the philosophy of a cancer cell". What do I mean by that? **Think** before expanding. Think about scope creep, simplicity over complexity, overhead, etc. Not only think about "does this make sense" but "Is this a good next step". Maybe you don't need to make another feature, but reconcile, write some notes, see where you're at, document, clean up, optimize, tidy code up and write a blog post. 

#### Repeat

Rinse and repeat. The last step, but also the first. This is, by far, the best characteristic of a good learner, and something I like to think I do well enough. Repeating, in this context, means to never stop searching for something new to learn. Repeating is going back to step one. It's making new things, be it entirely new projects or refactoring old ones. This step is where you catch a break before routing back to your next adventure,

## Conclusions

Make a checkpoint every once in a while, as that allows you to see what you've done, so you can plan head. Take a step back and see how far you've come. Set goals for the future, but remember, as Jimmy Carr said, "It's not the pursuit of happiness, it's the happiness of the pursuit", so go slow, but steady, and learn everything you can. Learning can manifest in many ways: making new projects, refactoring old ones, talking to new people, listening to old ones, reading a new book or revisiting old classics. What matters is to never stop. Your brain needs to learn every single day to stay healthy, as does any muscle. 

This ended up being a mix on a summary of how I approach learning and a guide to learn (super biased), as I changed tones mid-way, but still, it's a good recap nonetheless.