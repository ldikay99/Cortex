# Benchmark de memoria (LoCoMo)

Conjunto: snap-research/locomo `3eb6f2c5`, 10 conversaciones (muestras 0, 1, 2, 3, 4, 5, 6, 7, 8, 9), 1536 preguntas (sin adversariales), todo local: sin IA ni tokens de API.

## Léxico (por defecto, sin modelos)

Tiempo total 118s (análisis e índice incluidos).

| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |
|---|---|---|---|---|---|---|---|
| una sola pista | 841 | 1000 | 0.929 | 0.924 | 0.986 | 958 | 18 |
| una sola pista | 841 | 2000 | 0.967 | 0.964 | 0.996 | 1923 | 18 |
| una sola pista | 841 | 4000 | 0.983 | 0.983 | 0.998 | 3855 | 37 |
| varias pistas | 282 | 1000 | 0.583 | 0.330 | 0.748 | 958 | 17 |
| varias pistas | 282 | 2000 | 0.721 | 0.496 | 0.885 | 1924 | 18 |
| varias pistas | 282 | 4000 | 0.834 | 0.635 | 0.960 | 3857 | 23 |
| temporal | 321 | 1000 | 0.870 | 0.847 | 0.944 | 959 | 18 |
| temporal | 321 | 2000 | 0.908 | 0.885 | 0.990 | 1926 | 18 |
| temporal | 321 | 4000 | 0.972 | 0.956 | 1.000 | 3862 | 32 |
| dominio abierto | 92 | 1000 | 0.468 | 0.402 | 0.689 | 955 | 19 |
| dominio abierto | 92 | 2000 | 0.605 | 0.511 | 0.859 | 1921 | 18 |
| dominio abierto | 92 | 4000 | 0.725 | 0.609 | 0.956 | 3851 | 23 |
| **global** | 1536 | 1000 | 0.826 | 0.768 | 0.915 | 958 | 18 |
| **global** | 1536 | 2000 | 0.888 | 0.835 | 0.966 | 1924 | 18 |
| **global** | 1536 | 4000 | 0.938 | 0.891 | 0.989 | 3857 | 33 |

### Ajuste (muestras 0-4)

| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |
|---|---|---|---|---|---|---|---|
| una sola pista | 418 | 1000 | 0.915 | 0.909 | 0.990 | 959 | 16 |
| una sola pista | 418 | 2000 | 0.956 | 0.955 | 1.000 | 1925 | 18 |
| una sola pista | 418 | 4000 | 0.978 | 0.978 | 1.000 | 3859 | 25 |
| varias pistas | 142 | 1000 | 0.590 | 0.373 | 0.764 | 958 | 17 |
| varias pistas | 142 | 2000 | 0.738 | 0.535 | 0.890 | 1926 | 18 |
| varias pistas | 142 | 4000 | 0.860 | 0.669 | 0.964 | 3859 | 23 |
| temporal | 156 | 1000 | 0.908 | 0.891 | 0.966 | 960 | 18 |
| temporal | 156 | 2000 | 0.932 | 0.917 | 1.000 | 1928 | 18 |
| temporal | 156 | 4000 | 0.992 | 0.981 | 1.000 | 3866 | 42 |
| dominio abierto | 44 | 1000 | 0.508 | 0.432 | 0.674 | 957 | 19 |
| dominio abierto | 44 | 2000 | 0.697 | 0.614 | 0.847 | 1924 | 18 |
| dominio abierto | 44 | 4000 | 0.775 | 0.682 | 0.932 | 3859 | 23 |
| **global** | 760 | 1000 | 0.829 | 0.778 | 0.925 | 959 | 17 |
| **global** | 760 | 2000 | 0.895 | 0.849 | 0.971 | 1926 | 18 |
| **global** | 760 | 4000 | 0.947 | 0.904 | 0.989 | 3860 | 28 |

### Control (muestras 5-9, no usadas para afinar)

| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |
|---|---|---|---|---|---|---|---|
| una sola pista | 423 | 1000 | 0.943 | 0.939 | 0.981 | 956 | 20 |
| una sola pista | 423 | 2000 | 0.979 | 0.974 | 0.993 | 1921 | 19 |
| una sola pista | 423 | 4000 | 0.988 | 0.988 | 0.995 | 3851 | 50 |
| varias pistas | 140 | 1000 | 0.575 | 0.286 | 0.731 | 958 | 17 |
| varias pistas | 140 | 2000 | 0.703 | 0.457 | 0.881 | 1923 | 18 |
| varias pistas | 140 | 4000 | 0.808 | 0.600 | 0.956 | 3856 | 23 |
| temporal | 165 | 1000 | 0.835 | 0.806 | 0.923 | 958 | 18 |
| temporal | 165 | 2000 | 0.885 | 0.855 | 0.980 | 1923 | 18 |
| temporal | 165 | 4000 | 0.954 | 0.933 | 1.000 | 3859 | 23 |
| dominio abierto | 48 | 1000 | 0.431 | 0.375 | 0.703 | 953 | 18 |
| dominio abierto | 48 | 2000 | 0.521 | 0.417 | 0.871 | 1919 | 18 |
| dominio abierto | 48 | 4000 | 0.679 | 0.542 | 0.979 | 3844 | 23 |
| **global** | 776 | 1000 | 0.822 | 0.758 | 0.906 | 957 | 19 |
| **global** | 776 | 2000 | 0.881 | 0.821 | 0.962 | 1921 | 18 |
| **global** | 776 | 4000 | 0.929 | 0.879 | 0.988 | 3853 | 37 |

## Léxico + embeddings locales (`minishlab/potion-base-8M@bf8b056651a2c21b8d2565580b8569da283cab23`)

Tiempo total 109s (análisis e índice incluidos).

| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |
|---|---|---|---|---|---|---|---|
| una sola pista | 841 | 1000 | 0.931 | 0.926 | 0.990 | 959 | 19 |
| una sola pista | 841 | 2000 | 0.971 | 0.969 | 0.998 | 1925 | 19 |
| una sola pista | 841 | 4000 | 0.989 | 0.989 | 1.000 | 3858 | 24 |
| varias pistas | 282 | 1000 | 0.615 | 0.362 | 0.769 | 959 | 18 |
| varias pistas | 282 | 2000 | 0.757 | 0.546 | 0.907 | 1926 | 23 |
| varias pistas | 282 | 4000 | 0.860 | 0.688 | 0.970 | 3861 | 24 |
| temporal | 321 | 1000 | 0.887 | 0.857 | 0.955 | 960 | 19 |
| temporal | 321 | 2000 | 0.933 | 0.913 | 0.990 | 1928 | 22 |
| temporal | 321 | 4000 | 0.974 | 0.960 | 1.000 | 3865 | 25 |
| dominio abierto | 92 | 1000 | 0.528 | 0.467 | 0.727 | 957 | 21 |
| dominio abierto | 92 | 2000 | 0.647 | 0.554 | 0.876 | 1921 | 20 |
| dominio abierto | 92 | 4000 | 0.774 | 0.663 | 0.954 | 3853 | 24 |
| **global** | 1536 | 1000 | 0.840 | 0.781 | 0.927 | 959 | 19 |
| **global** | 1536 | 2000 | 0.905 | 0.855 | 0.972 | 1925 | 21 |
| **global** | 1536 | 4000 | 0.949 | 0.908 | 0.992 | 3860 | 24 |

### Ajuste (muestras 0-4)

| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |
|---|---|---|---|---|---|---|---|
| una sola pista | 418 | 1000 | 0.917 | 0.911 | 0.990 | 960 | 20 |
| una sola pista | 418 | 2000 | 0.959 | 0.957 | 1.000 | 1927 | 19 |
| una sola pista | 418 | 4000 | 0.986 | 0.986 | 1.000 | 3862 | 24 |
| varias pistas | 142 | 1000 | 0.622 | 0.394 | 0.778 | 959 | 19 |
| varias pistas | 142 | 2000 | 0.772 | 0.570 | 0.917 | 1927 | 28 |
| varias pistas | 142 | 4000 | 0.869 | 0.718 | 0.974 | 3863 | 25 |
| temporal | 156 | 1000 | 0.923 | 0.904 | 0.985 | 961 | 19 |
| temporal | 156 | 2000 | 0.951 | 0.936 | 1.000 | 1930 | 26 |
| temporal | 156 | 4000 | 0.979 | 0.968 | 1.000 | 3868 | 25 |
| dominio abierto | 44 | 1000 | 0.591 | 0.545 | 0.737 | 960 | 22 |
| dominio abierto | 44 | 2000 | 0.701 | 0.636 | 0.884 | 1923 | 20 |
| dominio abierto | 44 | 4000 | 0.784 | 0.705 | 0.949 | 3860 | 25 |
| **global** | 760 | 1000 | 0.844 | 0.792 | 0.935 | 960 | 20 |
| **global** | 760 | 2000 | 0.908 | 0.862 | 0.978 | 1928 | 22 |
| **global** | 760 | 4000 | 0.951 | 0.916 | 0.992 | 3863 | 25 |

### Control (muestras 5-9, no usadas para afinar)

| categoría | preguntas | presupuesto | recall evidencia | todas halladas | acierto sesión | tokens medios | ms medios |
|---|---|---|---|---|---|---|---|
| una sola pista | 423 | 1000 | 0.946 | 0.941 | 0.991 | 957 | 17 |
| una sola pista | 423 | 2000 | 0.983 | 0.981 | 0.995 | 1923 | 19 |
| una sola pista | 423 | 4000 | 0.993 | 0.993 | 1.000 | 3855 | 23 |
| varias pistas | 140 | 1000 | 0.608 | 0.329 | 0.759 | 959 | 18 |
| varias pistas | 140 | 2000 | 0.741 | 0.521 | 0.897 | 1925 | 19 |
| varias pistas | 140 | 4000 | 0.850 | 0.657 | 0.966 | 3859 | 24 |
| temporal | 165 | 1000 | 0.853 | 0.812 | 0.926 | 958 | 20 |
| temporal | 165 | 2000 | 0.915 | 0.891 | 0.980 | 1925 | 19 |
| temporal | 165 | 4000 | 0.969 | 0.952 | 1.000 | 3861 | 24 |
| dominio abierto | 48 | 1000 | 0.471 | 0.396 | 0.718 | 956 | 20 |
| dominio abierto | 48 | 2000 | 0.599 | 0.479 | 0.868 | 1918 | 19 |
| dominio abierto | 48 | 4000 | 0.764 | 0.625 | 0.959 | 3846 | 24 |
| **global** | 776 | 1000 | 0.836 | 0.769 | 0.918 | 958 | 18 |
| **global** | 776 | 2000 | 0.901 | 0.848 | 0.966 | 1923 | 19 |
| **global** | 776 | 4000 | 0.948 | 0.901 | 0.991 | 3856 | 24 |

## Preguntas sin ninguna evidencia recuperada (presupuesto 2000, último modo)

- [una sola pista] muestra 0: How did Melanie feel about her family supporting her? (evidencia D18:13)
- [varias pistas] muestra 0: What do Melanie's kids like? (evidencia D4:8, D6:6)
- [una sola pista] muestra 0: What does Melanie think about Caroline's decision to adopt? (evidencia D2:15)
- [varias pistas] muestra 0: What is Caroline's identity? (evidencia D1:5)
- [una sola pista] muestra 0: What was the poetry reading that Caroline attended about? (evidencia D17:18)
- [dominio abierto] muestra 0: Would Melanie be more interested in going to a national park or a theme park? (evidencia D10:12, D10:14)
- [varias pistas] muestra 1: What do Jon and Gina both have in common? (evidencia D1:2, D1:3, D1:4, D2:1)
- [una sola pista] muestra 1: What do the dancers in the photo represent? (evidencia D1:25)
- [una sola pista] muestra 1: What does Gina say about the dancers in the photo? (evidencia D1:26)
- [una sola pista] muestra 1: What does Jon plan to do at the grand opening of his dance studio? (evidencia D15:9)
- [una sola pista] muestra 2: How often does John work out with his family? (evidencia D13:7)
- [dominio abierto] muestra 2: What attributes describe John? (evidencia D26:6, D2:14, D3:5, D4:6)
- [varias pistas] muestra 2: What items des John mention having as a child? (evidencia D3:15, D5:13)
- [dominio abierto] muestra 2: What job might Maria pursue in the future? (evidencia D11:10, D27:4, D32:14, D5:8)
- [una sola pista] muestra 2: What kind of activities did John and his mates from the online group do as part of their service efforts? (evidencia D3:5)
