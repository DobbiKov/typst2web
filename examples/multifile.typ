#set document(title: "Multi-file Example", author: "typst-to-web")
#set page(paper: "a4", margin: (x: 2.5cm, y: 3cm))
#set text(size: 11pt)
#set heading(numbering: "1.")

#align(center)[
  #text(size: 20pt, weight: "bold")[Multi-file Document]
  #v(0.5em)
  #text(size: 12pt, fill: gray)[Demonstrating multi-file includes]
  #v(2em)
]

#include "sections/intro.typ"

#include "sections/calculus.typ"

= Conclusion

Both sections above were defined in separate `.typ` files under `sections/`
and pulled in via `#include`. The math expressions in each file — inline
like $f(x) = x^2$ and display blocks — are all preprocessed and rendered
correctly by typst-to-web.
