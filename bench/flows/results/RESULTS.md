# Córtex · benchmark de flujos entre componentes

Generado: 2026-10-20 · Córtex analizado con `analyze()` (sin git) · verdad de referencia: `bench/flows/labels/*.jsonl` (etiquetado manual independiente).

Un flujo cuenta como encontrado si Córtex une el nodo de origen con el de destino por aristas de flujo (`http`, `rpc`, `handles`, `event`, `data`, `env`, `depends`, según el tipo de etiqueta), directamente o a través de un nodo intermedio endpoint/topic/variable/tabla (máx. 2 saltos). No cuentan `contains`, `import`, `call` ni `cochange`.

## Exhaustividad (recall) por repo y tipo

Conjuntos: «ajuste ronda 1» = los 11 repos usados para afinar en la primera ronda; «ajuste ronda 2» = los 6 repos del antiguo control (`split = "control"`), usados para afinar en la segunda ronda; «ajuste ronda 3» = los 6 repos del examen final de la ronda 2 (`split = "control2"`), usados para afinar en la tercera; «ajuste ronda 4» = los 7 repos del examen ciego de la ronda 3 (`split = "control3"`), usados para afinar en la cuarta; «ajuste ronda 5» = los 7 repos del examen ciego de la ronda 4 (`split = "control4"`), usados para afinar en la quinta. Los conjuntos de `repos.toml` sin entrada en `SPLITS` o marcados en `BLIND` (exámenes ciegos pendientes, como `control5`) no se analizan salvo con `--only`.

| repo | conjunto | route | http | rpc | event | data | env | service | total |
|---|---|---|---|---|---|---|---|---|---|
| microservices-demo | ajuste ronda 1 | 100.0 % (12/12) | 90.9 % (10/11) | 100.0 % (25/25) |  |  | 100.0 % (29/29) | 100.0 % (16/16) | **98.9 %** (92/93) |
| full-stack-fastapi-template | ajuste ronda 1 | 100.0 % (29/29) | 100.0 % (40/40) |  |  | 95.2 % (20/21) | 100.0 % (21/21) | 100.0 % (4/4) | **99.1 %** (114/115) |
| koel | ajuste ronda 1 | 100.0 % (159/159) | 100.0 % (142/142) |  |  |  |  |  | **100.0 %** (301/301) |
| spring-petclinic-microservices | ajuste ronda 1 | 100.0 % (19/19) | 95.0 % (19/20) |  |  | 100.0 % (20/20) | 100.0 % (3/3) | 100.0 % (21/21) | **98.8 %** (82/83) |
| eShop | ajuste ronda 1 | 96.7 % (29/30) | 100.0 % (17/17) | 100.0 % (6/6) | 100.0 % (36/36) | 100.0 % (18/18) |  |  | **99.1 %** (106/107) |
| proshop_mern | ajuste ronda 1 | 100.0 % (27/27) | 100.0 % (23/23) |  |  | 100.0 % (32/32) |  |  | **100.0 %** (82/82) |
| wild-workouts | ajuste ronda 1 | 100.0 % (11/11) | 100.0 % (22/22) | 100.0 % (6/6) |  | 33.3 % (2/6) | 100.0 % (20/20) | 100.0 % (6/6) | **94.4 %** (67/71) |
| realworld-axum-sqlx | ajuste ronda 1 | 100.0 % (23/23) |  |  |  | 100.0 % (47/47) | 100.0 % (3/3) |  | **100.0 %** (73/73) |
| rails-realworld | ajuste ronda 1 | 100.0 % (18/18) |  |  |  | 82.1 % (23/28) |  |  | **89.1 %** (41/46) |
| phoenix-realworld | ajuste ronda 1 | 100.0 % (24/24) |  |  |  | 100.0 % (32/32) |  |  | **100.0 %** (56/56) |
| kotlinconf-app | ajuste ronda 1 | 100.0 % (31/31) | 100.0 % (13/13) |  |  | 100.0 % (18/18) | 100.0 % (6/6) | 100.0 % (4/4) | **100.0 %** (72/72) |
| ghostfolio | ajuste ronda 2 | 100.0 % (120/120) | 100.0 % (108/108) |  | 100.0 % (36/36) | 100.0 % (165/165) | 100.0 % (19/19) | 100.0 % (4/4) | **100.0 %** (452/452) |
| django-react-blog | ajuste ronda 2 | 100.0 % (22/22) | 100.0 % (8/8) |  |  | 100.0 % (29/29) | 100.0 % (4/4) | 91.7 % (11/12) | **98.7 %** (74/75) |
| go-coffeeshop | ajuste ronda 2 | 100.0 % (7/7) | 100.0 % (4/4) | 100.0 % (9/9) | 66.7 % (8/12) | 100.0 % (21/21) | 100.0 % (14/14) | 100.0 % (19/19) | **95.3 %** (82/86) |
| sb3-course | ajuste ronda 2 | 100.0 % (8/8) | 100.0 % (5/5) |  | 100.0 % (2/2) | 100.0 % (10/10) | 100.0 % (41/41) | 100.0 % (24/24) | **100.0 %** (90/90) |
| full-stack-flutter-app | ajuste ronda 2 | 100.0 % (26/26) | 100.0 % (17/17) |  |  | 100.0 % (52/52) |  |  | **100.0 %** (95/95) |
| aspire-samples | ajuste ronda 2 | 100.0 % (18/18) | 100.0 % (16/16) | 100.0 % (10/10) | 90.9 % (10/11) | 95.2 % (20/21) | 100.0 % (14/14) | 100.0 % (27/27) | **98.3 %** (115/117) |
| 8mb.local | ajuste ronda 3 | 100.0 % (46/46) | 100.0 % (54/54) |  | 100.0 % (13/13) |  | 100.0 % (41/41) |  | **100.0 %** (154/154) |
| tchatchers | ajuste ronda 3 | 100.0 % (14/14) | 87.5 % (14/16) |  | 100.0 % (17/17) | 100.0 % (31/31) | 100.0 % (11/11) | 100.0 % (16/16) | **98.1 %** (103/105) |
| NotyKT | ajuste ronda 3 | 100.0 % (10/10) | 100.0 % (16/16) |  |  | 100.0 % (26/26) | 100.0 % (34/34) | 100.0 % (1/1) | **100.0 %** (87/87) |
| terminus | ajuste ronda 3 | 100.0 % (40/40) |  |  | 100.0 % (11/11) | 100.0 % (40/40) | 100.0 % (21/21) | 100.0 % (10/10) | **100.0 %** (122/122) |
| quarkus-super-heroes | ajuste ronda 3 | 100.0 % (40/40) | 100.0 % (13/13) | 100.0 % (11/11) | 100.0 % (6/6) | 96.6 % (28/29) | 100.0 % (13/13) | 100.0 % (27/27) | **99.3 %** (138/139) |
| papermark | ajuste ronda 3 | 100.0 % (69/69) |  |  | 100.0 % (38/38) | 100.0 % (66/66) | 100.0 % (33/33) |  | **100.0 %** (206/206) |
| micronaut-microservices-poc | ajuste ronda 4 | 100.0 % (29/29) | 100.0 % (25/25) |  | 100.0 % (10/10) | 74.1 % (20/27) | 100.0 % (13/13) | 94.7 % (18/19) | **93.5 %** (115/123) |
| redash | ajuste ronda 4 | 100.0 % (28/28) | 96.4 % (27/28) |  | 100.0 % (38/38) | 100.0 % (23/23) | 100.0 % (13/13) | 100.0 % (10/10) | **99.3 %** (139/140) |
| woodpecker | ajuste ronda 4 | 100.0 % (45/45) | 100.0 % (35/35) | 100.0 % (14/14) | 0.0 % (0/12) | 100.0 % (25/25) | 100.0 % (15/15) | 66.7 % (2/3) | **91.3 %** (136/149) |
| plausible-analytics | ajuste ronda 4 | 100.0 % (51/51) |  |  | 100.0 % (29/29) | 100.0 % (28/28) | 100.0 % (31/31) |  | **100.0 %** (139/139) |
| outline | ajuste ronda 4 | 100.0 % (29/29) | 100.0 % (5/5) |  | 100.0 % (51/51) | 100.0 % (31/31) | 100.0 % (22/22) | 100.0 % (2/2) | **100.0 %** (140/140) |
| karakeep | ajuste ronda 4 | 100.0 % (13/13) | 100.0 % (11/11) | 100.0 % (25/25) | 100.0 % (32/32) | 100.0 % (24/24) | 100.0 % (12/12) | 100.0 % (29/29) | **100.0 %** (146/146) |
| Kavita | ajuste ronda 4 | 96.9 % (31/32) | 91.2 % (31/34) |  | 98.1 % (51/52) | 100.0 % (24/24) | 100.0 % (6/6) |  | **96.6 %** (143/148) |
| gotify | ajuste ronda 5 | 100.0 % (44/44) | 100.0 % (37/37) |  | 100.0 % (4/4) | 100.0 % (5/5) | 100.0 % (30/30) |  | **100.0 %** (120/120) |
| docmost | ajuste ronda 5 | 100.0 % (27/27) | 100.0 % (27/27) |  | 100.0 % (35/35) | 100.0 % (32/32) | 100.0 % (15/15) | 100.0 % (4/4) | **100.0 %** (140/140) |
| paperless-ngx | ajuste ronda 5 | 100.0 % (56/56) | 100.0 % (35/35) |  | 100.0 % (44/44) | 100.0 % (22/22) | 100.0 % (18/18) | 100.0 % (18/18) | **100.0 %** (193/193) |
| mastodon | ajuste ronda 5 | 100.0 % (47/47) | 100.0 % (28/28) |  | 100.0 % (62/62) | 100.0 % (31/31) | 100.0 % (16/16) | 100.0 % (6/6) | **100.0 %** (190/190) |
| vaultwarden | ajuste ronda 5 | 100.0 % (50/50) |  |  | 96.4 % (27/28) | 100.0 % (51/51) | 100.0 % (39/39) | 100.0 % (6/6) | **99.4 %** (173/174) |
| dependency-track | ajuste ronda 5 | 100.0 % (30/30) |  |  | 100.0 % (62/62) | 100.0 % (24/24) | 95.7 % (45/47) | 40.0 % (2/5) | **97.0 %** (163/168) |
| immich | ajuste ronda 5 | 100.0 % (29/29) | 100.0 % (57/57) | 97.3 % (36/37) | 100.0 % (72/72) | 100.0 % (15/15) | 100.0 % (25/25) | 68.4 % (13/19) | **97.2 %** (247/254) |
| **global** | | **99.8 % (1311/1313)** | **99.1 % (859/867)** | **99.3 % (142/143)** | **97.3 % (694/713)** | **98.2 % (1055/1074)** | **99.7 % (627/629)** | **96.2 % (300/312)** | **98.8 %** (4988/5051) |

### Resumen por conjunto

| conjunto | repos | route | http | rpc | event | data | env | service | total | media por repo | peor repo |
|---|---|---|---|---|---|---|---|---|---|---|---|
| ajuste ronda 1 | 11 | 99.7 % (382/383) | 99.3 % (286/288) | 100.0 % (37/37) | 100.0 % (36/36) | 95.5 % (212/222) | 100.0 % (82/82) | 100.0 % (51/51) | **98.8 %** (1086/1099) | 98.1 % | rails-realworld (89.1 %) |
| ajuste ronda 2 | 6 | 100.0 % (201/201) | 100.0 % (158/158) | 100.0 % (19/19) | 91.8 % (56/61) | 99.7 % (297/298) | 100.0 % (92/92) | 98.8 % (85/86) | **99.2 %** (908/915) | 98.7 % | go-coffeeshop (95.3 %) |
| ajuste ronda 3 | 6 | 100.0 % (219/219) | 98.0 % (97/99) | 100.0 % (11/11) | 100.0 % (85/85) | 99.5 % (191/192) | 100.0 % (153/153) | 100.0 % (54/54) | **99.6 %** (810/813) | 99.6 % | tchatchers (98.1 %) |
| ajuste ronda 4 | 7 | 99.6 % (226/227) | 97.1 % (134/138) | 100.0 % (39/39) | 94.2 % (211/224) | 96.2 % (175/182) | 100.0 % (112/112) | 96.8 % (61/63) | **97.3 %** (958/985) | 97.2 % | woodpecker (91.3 %) |
| ajuste ronda 5 | 7 | 100.0 % (283/283) | 100.0 % (184/184) | 97.3 % (36/37) | 99.7 % (306/307) | 100.0 % (180/180) | 98.9 % (188/190) | 84.5 % (49/58) | **99.0 %** (1226/1239) | 99.1 % | dependency-track (97.0 %) |

## Precisión estimada

Unidades: aristas de flujo de Córtex dentro del `scope`/`kinds` etiquetado de cada repo (lecturas de env desde código, no las definiciones). Una arista está *emparejada* si forma parte del camino de alguna etiqueta encontrada. De las no emparejadas se toma una muestra determinista (hasta 10 por repo, orden por hash) y se revisa leyendo el código: `fp` = conexión falsa, `ok` = flujo real que el etiquetado no recoge (omisión). Veredictos en `bench/flows/review.jsonl`.

- Aristas de flujo en alcance: 17430 · emparejadas: 5627 · sin emparejar: 11803
- Muestra revisada: 330 · falsos positivos: 5 (2 % de las no emparejadas)
- Cota inferior (solo emparejadas): 32.3 % · **precisión estimada: 99.0 %** · conservadora (tasa de FP de la muestra + 3/n, regla del tres al 95 %): 98.4 %

| conjunto | aristas | emparejadas | muestra revisada | fp | precisión estimada | conservadora |
|---|---|---|---|---|---|---|
| ajuste ronda 1 | 1474 | 75.3 % | 79 | 0 | 100.0 % | 99.1 % |
| ajuste ronda 2 | 1369 | 73.1 % | 58 | 1 | 99.5 % | 98.1 % |
| ajuste ronda 3 | 1557 | 54.5 % | 53 | 1 | 99.1 % | 96.6 % |
| ajuste ronda 4 | 4597 | 24.0 % | 70 | 3 | 96.7 % | 93.5 % |
| ajuste ronda 5 | 8433 | 18.5 % | 70 | 0 | 100.0 % | 96.5 % |

| repo | conjunto | aristas | emparejadas | por tipo (emparejadas/total) |
|---|---|---|---|---|
| microservices-demo | ajuste ronda 1 | 242 | 38.8 % | route 12/19 · http 10/11 · rpc 25/84 · env 31/93 · service 16/35 |
| full-stack-fastapi-template | ajuste ronda 1 | 166 | 60.2 % | route 29/29 · http 40/40 · data 17/26 · env 11/60 · service 3/11 |
| koel | ajuste ronda 1 | 317 | 99.1 % | route 174/174 · http 140/143 |
| spring-petclinic-microservices | ajuste ronda 1 | 116 | 69.0 % | route 20/20 · http 19/19 · data 20/48 · service 21/29 |
| eShop | ajuste ronda 1 | 159 | 74.2 % | route 30/46 · http 17/18 · rpc 9/15 · event 49/49 · data 13/31 |
| proshop_mern | ajuste ronda 1 | 79 | 98.7 % | route 27/28 · http 23/23 · data 28/28 |
| wild-workouts | ajuste ronda 1 | 116 | 69.0 % | route 13/13 · http 33/35 · rpc 4/11 · data 2/2 · env 20/30 · service 8/25 |
| realworld-axum-sqlx | ajuste ronda 1 | 72 | 100.0 % | route 23/23 · data 46/46 · env 3/3 |
| rails-realworld | ajuste ronda 1 | 47 | 89.4 % | route 20/20 · data 22/27 |
| phoenix-realworld | ajuste ronda 1 | 75 | 76.0 % | route 27/39 · data 30/36 |
| kotlinconf-app | ajuste ronda 1 | 85 | 88.2 % | route 31/31 · http 13/13 · data 14/24 · env 13/13 · service 4/4 |
| ghostfolio | ajuste ronda 2 | 706 | 80.3 % | route 120/120 · http 108/115 · event 35/36 · data 284/315 · env 16/115 · service 4/5 |
| django-react-blog | ajuste ronda 2 | 82 | 90.2 % | route 25/25 · http 8/9 · data 28/29 · env 4/6 · service 9/13 |
| go-coffeeshop | ajuste ronda 2 | 100 | 75.0 % | route 5/7 · http 4/4 · rpc 13/13 · event 8/8 · data 21/32 · env 14/25 · service 10/11 |
| sb3-course | ajuste ronda 2 | 209 | 25.4 % | route 8/8 · http 5/5 · event 2/2 · data 10/10 · env 4/4 · service 24/180 |
| full-stack-flutter-app | ajuste ronda 2 | 127 | 87.4 % | route 26/26 · http 17/17 · data 68/84 |
| aspire-samples | ajuste ronda 2 | 145 | 83.4 % | route 18/27 · http 15/15 · rpc 14/14 · event 13/13 · data 15/15 · env 26/40 · service 20/21 |
| 8mb.local | ajuste ronda 3 | 247 | 62.3 % | route 46/53 · http 52/53 · event 15/22 · env 41/119 |
| tchatchers | ajuste ronda 3 | 153 | 64.1 % | route 14/14 · http 13/13 · event 22/22 · data 30/81 · env 11/15 · service 8/8 |
| NotyKT | ajuste ronda 3 | 69 | 95.7 % | route 10/10 · http 14/14 · data 25/26 · env 16/17 · service 1/2 |
| terminus | ajuste ronda 3 | 311 | 56.6 % | route 40/131 · event 17/18 · data 98/112 · env 11/38 · service 10/12 |
| quarkus-super-heroes | ajuste ronda 3 | 200 | 66.0 % | route 40/40 · http 13/20 · rpc 11/11 · event 8/8 · data 31/36 · env 2/4 · service 27/81 |
| papermark | ajuste ronda 3 | 577 | 38.5 % | route 69/69 · event 44/46 · data 89/424 · env 20/38 |
| micronaut-microservices-poc | ajuste ronda 4 | 145 | 77.9 % | route 29/29 · http 25/36 · event 7/9 · data 22/38 · env 12/14 · service 18/19 |
| redash | ajuste ronda 4 | 598 | 24.7 % | route 28/130 · http 27/27 · event 51/53 · data 23/240 · env 9/138 · service 10/10 |
| woodpecker | ajuste ronda 4 | 316 | 42.4 % | route 47/116 · http 35/89 · rpc 12/24 · data 25/58 · env 14/28 · service 1/1 |
| plausible-analytics | ajuste ronda 4 | 857 | 23.1 % | route 51/243 · event 56/62 · data 60/451 · env 31/101 |
| outline | ajuste ronda 4 | 894 | 22.6 % | route 29/97 · http 5/61 · event 99/201 · data 16/439 · env 51/94 · service 2/2 |
| karakeep | ajuste ronda 4 | 796 | 20.1 % | route 26/173 · http 11/17 · rpc 25/98 · event 45/78 · data 22/344 · env 6/52 · service 25/34 |
| Kavita | ajuste ronda 4 | 991 | 15.1 % | route 31/522 · http 31/32 · event 51/99 · data 37/334 · env 0/4 |
| gotify | ajuste ronda 5 | 203 | 94.1 % | route 44/46 · http 37/37 · event 7/10 · data 5/11 · env 98/99 |
| docmost | ajuste ronda 5 | 311 | 44.1 % | route 27/42 · http 27/34 · event 39/46 · data 30/151 · env 12/35 · service 2/3 |
| paperless-ngx | ajuste ronda 5 | 658 | 36.5 % | route 55/144 · http 35/49 · event 51/83 · data 19/172 · env 66/186 · service 14/24 |
| mastodon | ajuste ronda 5 | 3430 | 6.6 % | route 53/647 · http 26/149 · event 92/523 · data 31/1849 · env 20/254 · service 6/8 |
| vaultwarden | ajuste ronda 5 | 861 | 31.9 % | route 50/166 · event 39/40 · data 45/462 · env 135/184 · service 6/9 |
| dependency-track | ajuste ronda 5 | 494 | 42.1 % | route 30/110 · event 119/143 · data 24/205 · env 34/35 · service 1/1 |
| immich | ajuste ronda 5 | 2476 | 11.5 % | route 29/29 · http 55/633 · rpc 36/101 · event 79/377 · data 30/1264 · env 42/52 · service 13/20 |

## Línea base (antes de los cambios en Córtex)

Primera ejecución del arnés sobre el Córtex de partida (solo los repos de la ronda 1). Aquella versión del arnés aceptaba además caminos por claves foráneas entre tablas (`ref`) y cualquier tipo de arista para cualquier etiqueta, así que la base está, si acaso, algo inflada.

| repo | línea base | final |
|---|---|---|
| microservices-demo | 75.3 % | 98.9 % |
| full-stack-fastapi-template | 20.9 % | 99.1 % |
| koel | 71.8 % | 100.0 % |
| spring-petclinic-microservices | 25.3 % | 98.8 % |
| eShop | 28.0 % | 99.1 % |
| proshop_mern | 56.1 % | 100.0 % |
| wild-workouts | 5.6 % | 94.4 % |
| realworld-axum-sqlx | 35.6 % | 100.0 % |
| rails-realworld | 37.0 % | 89.1 % |
| phoenix-realworld | 0.0 % | 100.0 % |
| kotlinconf-app | 0.0 % | 100.0 % |
| **global** | 41.3 % | 98.8 % |

## Ronda 2 (antes → después)

Ejecución del arnés al empezar la ronda 2 (Córtex al final de la ronda 1, mismas etiquetas salvo las correcciones documentadas en el README) frente a la actual.

| repo | conjunto | antes | después |
|---|---|---|---|
| microservices-demo | ajuste ronda 1 | 98.9 % (92/93) | 98.9 % (92/93) |
| full-stack-fastapi-template | ajuste ronda 1 | 99.1 % (114/115) | 99.1 % (114/115) |
| koel | ajuste ronda 1 | 100.0 % (301/301) | 100.0 % (301/301) |
| spring-petclinic-microservices | ajuste ronda 1 | 98.8 % (82/83) | 98.8 % (82/83) |
| eShop | ajuste ronda 1 | 99.1 % (106/107) | 99.1 % (106/107) |
| proshop_mern | ajuste ronda 1 | 100.0 % (82/82) | 100.0 % (82/82) |
| wild-workouts | ajuste ronda 1 | 94.4 % (67/71) | 94.4 % (67/71) |
| realworld-axum-sqlx | ajuste ronda 1 | 100.0 % (73/73) | 100.0 % (73/73) |
| rails-realworld | ajuste ronda 1 | 89.1 % (41/46) | 89.1 % (41/46) |
| phoenix-realworld | ajuste ronda 1 | 100.0 % (56/56) | 100.0 % (56/56) |
| kotlinconf-app | ajuste ronda 1 | 100.0 % (72/72) | 100.0 % (72/72) |
| ghostfolio | ajuste ronda 2 | 11.7 % (53/452) | 100.0 % (452/452) |
| django-react-blog | ajuste ronda 2 | 54.7 % (41/75) | 98.7 % (74/75) |
| go-coffeeshop | ajuste ronda 2 | 34.9 % (30/86) | 95.3 % (82/86) |
| sb3-course | ajuste ronda 2 | 25.6 % (23/90) | 100.0 % (90/90) |
| full-stack-flutter-app | ajuste ronda 2 | 0.0 % (0/95) | 100.0 % (95/95) |
| aspire-samples | ajuste ronda 2 | 39.3 % (46/117) | 98.3 % (115/117) |
| **ajuste ronda 1** | | **98.8 %** (1086/1099) | **98.8 %** (1086/1099) |
| **ajuste ronda 2** | | **21.1 %** (193/915) | **99.2 %** (908/915) |

## Ronda 3 (antes → después)

Ejecución del arnés al empezar la ronda 3 (Córtex al final de la ronda 2, mismas etiquetas) frente a la actual, con el tiempo de `analyze()` de cada repo en segundos (medido intercalando el `bridges.py` de partida y el actual dos veces en la misma máquina; se guarda el mínimo de cada uno).

| repo | conjunto | antes | después | s antes | s después |
|---|---|---|---|---|---|
| microservices-demo | ajuste ronda 1 | 98.9 % (92/93) | 98.9 % (92/93) | 2.87 | 3.3 |
| full-stack-fastapi-template | ajuste ronda 1 | 99.1 % (114/115) | 99.1 % (114/115) | 2.46 | 2.9 |
| koel | ajuste ronda 1 | 100.0 % (301/301) | 100.0 % (301/301) | 24.22 | 28.8 |
| spring-petclinic-microservices | ajuste ronda 1 | 98.8 % (82/83) | 98.8 % (82/83) | 1.78 | 1.7 |
| eShop | ajuste ronda 1 | 99.1 % (106/107) | 99.1 % (106/107) | 10.36 | 11.5 |
| proshop_mern | ajuste ronda 1 | 100.0 % (82/82) | 100.0 % (82/82) | 0.51 | 0.7 |
| wild-workouts | ajuste ronda 1 | 94.4 % (67/71) | 94.4 % (67/71) | 2.18 | 2.5 |
| realworld-axum-sqlx | ajuste ronda 1 | 100.0 % (73/73) | 100.0 % (73/73) | 0.25 | 0.3 |
| rails-realworld | ajuste ronda 1 | 89.1 % (41/46) | 89.1 % (41/46) | 0.36 | 0.4 |
| phoenix-realworld | ajuste ronda 1 | 100.0 % (56/56) | 100.0 % (56/56) | 0.43 | 0.5 |
| kotlinconf-app | ajuste ronda 1 | 100.0 % (72/72) | 100.0 % (72/72) | 5.37 | 10.8 |
| ghostfolio | ajuste ronda 2 | 100.0 % (452/452) | 100.0 % (452/452) | 19.17 | 28.1 |
| django-react-blog | ajuste ronda 2 | 98.7 % (74/75) | 98.7 % (74/75) | 0.98 | 1.5 |
| go-coffeeshop | ajuste ronda 2 | 95.3 % (82/86) | 95.3 % (82/86) | 1.02 | 1.3 |
| sb3-course | ajuste ronda 2 | 100.0 % (90/90) | 100.0 % (90/90) | 1.31 | 1.7 |
| full-stack-flutter-app | ajuste ronda 2 | 98.9 % (94/95) | 100.0 % (95/95) | 5.76 | 8.3 |
| aspire-samples | ajuste ronda 2 | 98.3 % (115/117) | 98.3 % (115/117) | 8.0 | 11.3 |
| 8mb.local | ajuste ronda 3 | 92.2 % (142/154) | 100.0 % (154/154) | 4.95 | 7.0 |
| tchatchers | ajuste ronda 3 | 62.9 % (66/105) | 98.1 % (103/105) | 1.43 | 1.8 |
| NotyKT | ajuste ronda 3 | 71.3 % (62/87) | 100.0 % (87/87) | 5.42 | 5.8 |
| terminus | ajuste ronda 3 | 4.1 % (5/122) | 100.0 % (122/122) | 8.93 | 17.0 |
| quarkus-super-heroes | ajuste ronda 3 | 13.7 % (19/139) | 99.3 % (138/139) | 9.5 | 13.7 |
| papermark | ajuste ronda 3 | 80.1 % (165/206) | 100.0 % (206/206) | 22.05 | 32.7 |
| **ajuste ronda 1** | | **98.8 %** (1086/1099) | **98.8 %** (1086/1099) | 50.8 | 63.4 |
| **ajuste ronda 2** | | **99.1 %** (907/915) | **99.2 %** (908/915) | 36.2 | 52.2 |
| **ajuste ronda 3** | | **56.5 %** (459/813) | **99.6 %** (810/813) | 52.3 | 78.0 |

Ajuste ronda 3 por tipo (antes → después):

| repo | route | http | rpc | event | data | env | service |
|---|---|---|---|---|---|---|---|
| 8mb.local | 46/46 → 46/46 | 51/54 → 54/54 |  | 6/13 → 13/13 |  | 39/41 → 41/41 |  |
| tchatchers | 14/14 → 14/14 | 0/16 → 14/16 |  | 0/17 → 17/17 | 25/31 → 31/31 | 11/11 → 11/11 | 16/16 → 16/16 |
| NotyKT | 10/10 → 10/10 | 8/16 → 16/16 |  |  | 10/26 → 26/26 | 33/34 → 34/34 | 1/1 → 1/1 |
| terminus | 0/40 → 40/40 |  |  | 0/11 → 11/11 | 0/40 → 40/40 | 1/21 → 21/21 | 4/10 → 10/10 |
| quarkus-super-heroes | 0/40 → 40/40 | 0/13 → 13/13 | 0/11 → 11/11 | 0/6 → 6/6 | 8/29 → 28/29 | 11/13 → 13/13 | 0/27 → 27/27 |
| papermark | 66/69 → 69/69 |  |  | 0/38 → 38/38 | 66/66 → 66/66 | 33/33 → 33/33 |  |
| **total** | **62.1 % → 100.0 %** | **59.6 % → 98.0 %** | **0.0 % → 100.0 %** | **7.1 % → 100.0 %** | **56.8 % → 99.5 %** | **83.7 % → 100.0 %** | **38.9 % → 100.0 %** |

## Ronda 4 (antes → después)

Ejecución del arnés al empezar la ronda 4 (Córtex al final de la ronda 3, mismas etiquetas) frente a la actual. Los segundos de «antes» y «después» son el tiempo de `analyze()` medido intercalando el `bridges.py` de partida y el actual dos veces en la misma máquina (mínimo de cada uno); ver el README.

| repo | conjunto | antes | después | s antes | s después |
|---|---|---|---|---|---|
| microservices-demo | ajuste ronda 1 | 98.9 % (92/93) | 98.9 % (92/93) | 3.1 | 3.4 |
| full-stack-fastapi-template | ajuste ronda 1 | 99.1 % (114/115) | 99.1 % (114/115) | 2.6 | 2.8 |
| koel | ajuste ronda 1 | 100.0 % (301/301) | 100.0 % (301/301) | 26.7 | 28.6 |
| spring-petclinic-microservices | ajuste ronda 1 | 98.8 % (82/83) | 98.8 % (82/83) | 1.5 | 1.5 |
| eShop | ajuste ronda 1 | 99.1 % (106/107) | 99.1 % (106/107) | 10.1 | 10.7 |
| proshop_mern | ajuste ronda 1 | 100.0 % (82/82) | 100.0 % (82/82) | 0.6 | 0.6 |
| wild-workouts | ajuste ronda 1 | 94.4 % (67/71) | 94.4 % (67/71) | 2.3 | 2.3 |
| realworld-axum-sqlx | ajuste ronda 1 | 100.0 % (73/73) | 100.0 % (73/73) | 0.3 | 0.3 |
| rails-realworld | ajuste ronda 1 | 89.1 % (41/46) | 89.1 % (41/46) | 0.4 | 0.4 |
| phoenix-realworld | ajuste ronda 1 | 100.0 % (56/56) | 100.0 % (56/56) | 0.5 | 0.5 |
| kotlinconf-app | ajuste ronda 1 | 100.0 % (72/72) | 100.0 % (72/72) | 5.5 | 5.7 |
| ghostfolio | ajuste ronda 2 | 100.0 % (452/452) | 100.0 % (452/452) | 19.5 | 20.5 |
| django-react-blog | ajuste ronda 2 | 98.7 % (74/75) | 98.7 % (74/75) | 0.9 | 1.0 |
| go-coffeeshop | ajuste ronda 2 | 95.3 % (82/86) | 95.3 % (82/86) | 1.0 | 1.0 |
| sb3-course | ajuste ronda 2 | 100.0 % (90/90) | 100.0 % (90/90) | 1.2 | 1.2 |
| full-stack-flutter-app | ajuste ronda 2 | 98.9 % (94/95) | 100.0 % (95/95) | 6.8 | 6.5 |
| aspire-samples | ajuste ronda 2 | 98.3 % (115/117) | 98.3 % (115/117) | 8.2 | 8.4 |
| 8mb.local | ajuste ronda 3 | 100.0 % (154/154) | 100.0 % (154/154) | 6.1 | 6.5 |
| tchatchers | ajuste ronda 3 | 98.1 % (103/105) | 98.1 % (103/105) | 1.5 | 1.7 |
| NotyKT | ajuste ronda 3 | 100.0 % (87/87) | 100.0 % (87/87) | 5.5 | 5.3 |
| terminus | ajuste ronda 3 | 99.2 % (121/122) | 100.0 % (122/122) | 10.3 | 13.0 |
| quarkus-super-heroes | ajuste ronda 3 | 99.3 % (138/139) | 99.3 % (138/139) | 10.4 | 13.2 |
| papermark | ajuste ronda 3 | 100.0 % (206/206) | 100.0 % (206/206) | 25.3 | 27.7 |
| micronaut-microservices-poc | ajuste ronda 4 | 26.0 % (32/123) | 93.5 % (115/123) | 5.1 | 4.8 |
| redash | ajuste ronda 4 | 5.7 % (8/140) | 99.3 % (139/140) | 16.3 | 18.5 |
| woodpecker | ajuste ronda 4 | 36.9 % (55/149) | 91.3 % (136/149) | 25.1 | 25.4 |
| plausible-analytics | ajuste ronda 4 | 81.3 % (113/139) | 100.0 % (139/139) | 24.0 | 26.4 |
| outline | ajuste ronda 4 | 2.1 % (3/140) | 100.0 % (140/140) | 27.4 | 32.1 |
| karakeep | ajuste ronda 4 | 4.1 % (6/146) | 100.0 % (146/146) | 28.8 | 31.1 |
| Kavita | ajuste ronda 4 | 41.9 % (62/148) | 96.6 % (143/148) | 151.1 | 156.2 |
| **ajuste ronda 1** | | **98.8 %** (1086/1099) | **98.8 %** (1086/1099) | 53.6 | 56.8 |
| **ajuste ronda 2** | | **99.1 %** (907/915) | **99.2 %** (908/915) | 37.6 | 38.6 |
| **ajuste ronda 3** | | **99.5 %** (809/813) | **99.6 %** (810/813) | 59.1 | 67.4 |
| **ajuste ronda 4** | | **28.3 %** (279/985) | **97.3 %** (958/985) | 277.8 | 294.5 |

Ajuste ronda 4 por tipo (antes → después):

| repo | route | http | rpc | event | data | env | service |
|---|---|---|---|---|---|---|---|
| micronaut-microservices-poc | 14/29 → 29/29 | 4/25 → 25/25 |  | 2/10 → 10/10 | 12/27 → 20/27 | 0/13 → 13/13 | 0/19 → 18/19 |
| redash | 0/28 → 28/28 | 0/28 → 27/28 |  | 1/38 → 38/38 | 0/23 → 23/23 | 0/13 → 13/13 | 7/10 → 10/10 |
| woodpecker | 41/45 → 45/45 | 0/35 → 35/35 | 12/14 → 14/14 | 0/12 → 0/12 | 0/25 → 25/25 | 0/15 → 15/15 | 2/3 → 2/3 |
| plausible-analytics | 46/51 → 51/51 |  |  | 8/29 → 29/29 | 28/28 → 28/28 | 31/31 → 31/31 |  |
| outline | 1/29 → 29/29 | 0/5 → 5/5 |  | 0/51 → 51/51 | 0/31 → 31/31 | 0/22 → 22/22 | 2/2 → 2/2 |
| karakeep | 0/13 → 13/13 | 0/11 → 11/11 | 0/25 → 25/25 | 0/32 → 32/32 | 0/24 → 24/24 | 0/12 → 12/12 | 6/29 → 29/29 |
| Kavita | 31/32 → 31/32 | 15/34 → 31/34 |  | 0/52 → 51/52 | 15/24 → 24/24 | 1/6 → 6/6 |  |
| **total** | **58.6 % → 99.6 %** | **13.8 % → 97.1 %** | **30.8 % → 100.0 %** | **4.9 % → 94.2 %** | **30.2 % → 96.2 %** | **28.6 % → 100.0 %** | **27.0 % → 96.8 %** |

## Ronda 5 (antes → después)

Ejecución del arnés al empezar la ronda 5 (Córtex al final de la ronda 4) frente a la actual, con las mismas reglas de puntuación y etiquetas que la ejecución final (ver «Ronda 5» en el README: dos correcciones de etiquetas y dos ajustes de puntuación). Los segundos son el tiempo de `analyze()` medido intercalando el `bridges.py`/`structural.py` de partida y el actual en la misma máquina (mínimo de dos pasadas) en los repos medidos; en el resto, el de la ejecución.

| repo | conjunto | antes | después | s antes | s después |
|---|---|---|---|---|---|
| microservices-demo | ajuste ronda 1 | 98.9 % (92/93) | 98.9 % (92/93) | 3.3 | 3.3 |
| full-stack-fastapi-template | ajuste ronda 1 | 99.1 % (114/115) | 99.1 % (114/115) | 2.9 | 2.9 |
| koel | ajuste ronda 1 | 100.0 % (301/301) | 100.0 % (301/301) | 36.0 | 28.8 |
| spring-petclinic-microservices | ajuste ronda 1 | 98.8 % (82/83) | 98.8 % (82/83) | 1.7 | 1.7 |
| eShop | ajuste ronda 1 | 99.1 % (106/107) | 99.1 % (106/107) | 30.0 | 11.5 |
| proshop_mern | ajuste ronda 1 | 100.0 % (82/82) | 100.0 % (82/82) | 0.7 | 0.7 |
| wild-workouts | ajuste ronda 1 | 94.4 % (67/71) | 94.4 % (67/71) | 2.5 | 2.5 |
| realworld-axum-sqlx | ajuste ronda 1 | 100.0 % (73/73) | 100.0 % (73/73) | 0.3 | 0.3 |
| rails-realworld | ajuste ronda 1 | 89.1 % (41/46) | 89.1 % (41/46) | 0.5 | 0.4 |
| phoenix-realworld | ajuste ronda 1 | 100.0 % (56/56) | 100.0 % (56/56) | 0.5 | 0.5 |
| kotlinconf-app | ajuste ronda 1 | 100.0 % (72/72) | 100.0 % (72/72) | 6.2 | 10.8 |
| ghostfolio | ajuste ronda 2 | 100.0 % (452/452) | 100.0 % (452/452) | 20.9 | 21.5 |
| django-react-blog | ajuste ronda 2 | 98.7 % (74/75) | 98.7 % (74/75) | 1.1 | 1.5 |
| go-coffeeshop | ajuste ronda 2 | 95.3 % (82/86) | 95.3 % (82/86) | 1.1 | 1.3 |
| sb3-course | ajuste ronda 2 | 100.0 % (90/90) | 100.0 % (90/90) | 1.3 | 1.7 |
| full-stack-flutter-app | ajuste ronda 2 | 98.9 % (94/95) | 100.0 % (95/95) | 21.0 | 8.3 |
| aspire-samples | ajuste ronda 2 | 98.3 % (115/117) | 98.3 % (115/117) | 9.6 | 11.3 |
| 8mb.local | ajuste ronda 3 | 100.0 % (154/154) | 100.0 % (154/154) | 7.6 | 7.0 |
| tchatchers | ajuste ronda 3 | 98.1 % (103/105) | 98.1 % (103/105) | 1.6 | 1.8 |
| NotyKT | ajuste ronda 3 | 100.0 % (87/87) | 100.0 % (87/87) | 5.8 | 5.8 |
| terminus | ajuste ronda 3 | 100.0 % (122/122) | 100.0 % (122/122) | 13.3 | 17.0 |
| quarkus-super-heroes | ajuste ronda 3 | 99.3 % (138/139) | 99.3 % (138/139) | 13.5 | 13.7 |
| papermark | ajuste ronda 3 | 100.0 % (206/206) | 100.0 % (206/206) | 28.2 | 32.7 |
| micronaut-microservices-poc | ajuste ronda 4 | 93.5 % (115/123) | 93.5 % (115/123) | 4.9 | 5.3 |
| redash | ajuste ronda 4 | 99.3 % (139/140) | 99.3 % (139/140) | 18.3 | 21.6 |
| woodpecker | ajuste ronda 4 | 91.3 % (136/149) | 91.3 % (136/149) | 28.1 | 42.4 |
| plausible-analytics | ajuste ronda 4 | 100.0 % (139/139) | 100.0 % (139/139) | 26.4 | 44.9 |
| outline | ajuste ronda 4 | 100.0 % (140/140) | 100.0 % (140/140) | 42.6 | 36.8 |
| karakeep | ajuste ronda 4 | 100.0 % (146/146) | 100.0 % (146/146) | 35.7 | 32.7 |
| Kavita | ajuste ronda 4 | 96.6 % (143/148) | 96.6 % (143/148) | 159.1 | 196.9 |
| gotify | ajuste ronda 5 | 36.7 % (44/120) | 100.0 % (120/120) | 3.4 | 4.0 |
| docmost | ajuste ronda 5 | 64.3 % (90/140) | 100.0 % (140/140) | 22.0 | 25.9 |
| paperless-ngx | ajuste ronda 5 | 50.3 % (97/193) | 100.0 % (193/193) | 31.7 | 34.6 |
| mastodon | ajuste ronda 5 | 84.7 % (161/190) | 100.0 % (190/190) | 53.5 | 55.3 |
| vaultwarden | ajuste ronda 5 | 32.2 % (56/174) | 99.4 % (173/174) | 11.2 | 12.4 |
| dependency-track | ajuste ronda 5 | 13.1 % (22/168) | 97.0 % (163/168) | 57.8 | 61.8 |
| immich | ajuste ronda 5 | 46.5 % (118/254) | 97.2 % (247/254) | 48.1 | 53.8 |
| **ajuste ronda 1** | | **98.8 %** (1086/1099) | **98.8 %** (1086/1099) | 84.6 | 63.4 |
| **ajuste ronda 2** | | **99.1 %** (907/915) | **99.2 %** (908/915) | 55.0 | 45.6 |
| **ajuste ronda 3** | | **99.6 %** (810/813) | **99.6 %** (810/813) | 70.0 | 78.0 |
| **ajuste ronda 4** | | **97.3 %** (958/985) | **97.3 %** (958/985) | 315.1 | 380.6 |
| **ajuste ronda 5** | | **47.5 %** (588/1239) | **99.0 %** (1226/1239) | 227.7 | 247.8 |

Ajuste ronda 5 por tipo (antes → después):

| repo | route | http | rpc | event | data | env | service |
|---|---|---|---|---|---|---|---|
| gotify | 24/44 → 44/44 | 20/37 → 37/37 |  | 0/4 → 4/4 | 0/5 → 5/5 | 0/30 → 30/30 |  |
| docmost | 27/27 → 27/27 | 27/27 → 27/27 |  | 17/35 → 35/35 | 0/32 → 32/32 | 15/15 → 15/15 | 4/4 → 4/4 |
| paperless-ngx | 45/56 → 56/56 | 16/35 → 35/35 |  | 18/44 → 44/44 | 0/22 → 22/22 | 0/18 → 18/18 | 18/18 → 18/18 |
| mastodon | 43/47 → 47/47 | 11/28 → 28/28 |  | 54/62 → 62/62 | 31/31 → 31/31 | 16/16 → 16/16 | 6/6 → 6/6 |
| vaultwarden | 50/50 → 50/50 |  |  | 0/28 → 27/28 | 0/51 → 51/51 | 0/39 → 39/39 | 6/6 → 6/6 |
| dependency-track | 14/30 → 30/30 |  |  | 2/62 → 62/62 | 0/24 → 24/24 | 4/47 → 45/47 | 2/5 → 2/5 |
| immich | 29/29 → 29/29 | 0/57 → 57/57 | 0/37 → 36/37 | 51/72 → 72/72 | 0/15 → 15/15 | 25/25 → 25/25 | 13/19 → 13/19 |
| **total** | **82.0 % → 100.0 %** | **40.2 % → 100.0 %** | **0.0 % → 97.3 %** | **46.3 % → 99.7 %** | **17.2 % → 100.0 %** | **31.6 % → 98.9 %** | **84.5 % → 84.5 %** |

### Muestra de aristas sin etiqueta

| repo | tipo | origen | destino | veredicto | nota |
|---|---|---|---|---|---|
| microservices-demo | env | src/cartservice/src/cartstore/AlloyDBCartStore.cs:25 AlloyDBCartStore | kustomize/components/alloydb/kustomization.yaml:34 ALLOYDB_PRIMARY_IP | ok | configuration["..."] (IConfiguration lee el entorno) en el almacen de carrito: lectura real |
| microservices-demo | env | src/productcatalogservice/catalog_loader.go:85 loadCatalogFromAlloyDB | kustomize/components/alloydb/kustomization.yaml:40 ALLOYDB_SECRET_NAME | ok | lectura real de la variable; solo se define en componentes kustomize (fuera de lo etiquetado) |
| microservices-demo | env | src/emailservice/email_server.py:1 email_server.py | kustomize/components/google-cloud-operations/kustomization.yaml:33 COLLECTOR_SERVICE_ADDR | ok | lectura real de la variable; solo se define en componentes kustomize (fuera de lo etiquetado) |
| microservices-demo | env | src/paymentservice/index.js:1 index.js | kustomize/components/google-cloud-operations/kustomization.yaml:33 COLLECTOR_SERVICE_ADDR | ok | lectura real de la variable; solo se define en componentes kustomize (fuera de lo etiquetado) |
| microservices-demo | rpc | src/paymentservice/proto/demo.proto:70 ProductCatalogService.ListProducts | protos/demo.proto:72 RPC hipstershop.ProductCatalogService/ListProducts | ok | copia del .proto del servicio: el rpc declarado es el mismo endpoint |
| microservices-demo | service | kubernetes-manifests/emailservice.yaml:71 Service/emailservice | kubernetes-manifests/emailservice.yaml:16 Deployment/emailservice | ok | flujo real fuera del etiquetado |
| microservices-demo | env | src/paymentservice/index.js:1 index.js | kustomize/components/google-cloud-operations/kustomization.yaml:35 OTEL_SERVICE_NAME | ok | lectura real de la variable; solo se define en componentes kustomize (fuera de lo etiquetado) |
| microservices-demo | env | src/frontend/handlers.go:59 frontendServer.homeHandler | helm-chart/templates/frontend.yaml:111 ENV_PLATFORM | ok | lectura real; la definicion vista es la del chart de Helm (fuera de lo etiquetado) |
| microservices-demo | rpc | src/currencyservice/proto/demo.proto:55 RecommendationService.ListRecommendations | protos/demo.proto:57 RPC hipstershop.RecommendationService/ListRecommendations | ok | copia del .proto del servicio: el rpc declarado es el mismo endpoint |
| microservices-demo | service | kubernetes-manifests/checkoutservice.yaml:78 Service/checkoutservice | kubernetes-manifests/checkoutservice.yaml:16 Deployment/checkoutservice | ok | flujo real fuera del etiquetado |
| full-stack-fastapi-template | data | backend/app/alembic/versions/d98dd8ec85a3_edit_replace_id_integers_in_all_models_.py:21 upgrade | backend/app/models.py:87 Item | ok | la migración ejecuta ALTER/SQL sobre la tabla: real |
| full-stack-fastapi-template | env | backend/app/utils.py:70 generate_reset_password_email | backend/app/core/config.py:57 EMAIL_RESET_TOKEN_EXPIRE_HOURS | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| full-stack-fastapi-template | service | compose.yml:49 backend | backend/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| full-stack-fastapi-template | env | backend/app/utils.py:34 send_email | .env:13 SMTP_TLS | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| full-stack-fastapi-template | env | backend/app/core/config.py:15 Settings | backend/app/core/config.py:43 SMTP_SSL | ok | campo de pydantic BaseSettings: lectura de entorno real (sin definicion en .env, por eso sin etiqueta) |
| full-stack-fastapi-template | env | backend/app/utils.py:34 send_email | backend/app/core/config.py:43 SMTP_SSL | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| full-stack-fastapi-template | env | backend/app/utils.py:34 send_email | backend/app/core/config.py:49 EMAILS_FROM_NAME | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| full-stack-fastapi-template | env | backend/app/core/config.py:61 Settings.emails_enabled | .env:11 SMTP_HOST | ok | flujo real fuera del etiquetado |
| full-stack-fastapi-template | env | backend/app/core/config.py:80 Settings._enforce_non_default_secrets | .env:6 SECRET_KEY | ok | flujo real fuera del etiquetado |
| full-stack-fastapi-template | env | backend/app/alembic/env.py:33 get_url | .env:18 DATABASE_URL | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| koel | http | resources/assets/js/services/downloadService.ts:1 downloadService.ts | routes/api.base.php:188 GET /api/songs/:song/download-url | ok | signedUrlService.fetch(`songs/${id}/download-url`): llamada real (omitida a proposito por URL firmada) |
| koel | http | resources/assets/js/stores/playableStore.ts:1 playableStore.ts | routes/api.base.php:210 GET /api/songs/in-folder | ok | http.get(`songs/in-folder${query}`): llamada real no etiquetada |
| koel | http | resources/assets/js/stores/radioStationStore.ts:1 radioStationStore.ts | routes/api.base.php:353 GET /api/radio/stations/:radioStation/stream-url | ok | signedUrlService.fetch(`radio/stations/${id}/stream-url`): llamada real (omitida a proposito) |
| spring-petclinic-microservices | data | spring-petclinic-vets-service/src/main/java/org/springframework/samples/petclinic/vets/model/Vet.java:38 Vet | spring-petclinic-vets-service/src/main/java/org/springframework/samples/petclinic/vets/model/Specialty.java:29 Specialty | ok | flujo real fuera del etiquetado |
| spring-petclinic-microservices | service | spring-petclinic-api-gateway/src/main/java/org/springframework/samples/petclinic/api/application/CustomersServiceClient.java:35 CustomersServiceClient.getOwner | docker-compose.yml:35 customers-service | ok | .uri("http://customers-service/...") -> servicio compose: real |
| spring-petclinic-microservices | service | spring-petclinic-admin-server/src/main/resources/application.yml:1 application.yml | docker-compose.yml:2 config-server | ok | spring.config.import configserver:http://config-server:8888: cableado real |
| spring-petclinic-microservices | data | spring-petclinic-customers-service/src/main/java/org/springframework/samples/petclinic/customers/model/PetRepository.java:35 PetRepository | spring-petclinic-customers-service/src/main/java/org/springframework/samples/petclinic/customers/model/PetType.java:27 PetType | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| spring-petclinic-microservices | service | spring-petclinic-api-gateway/src/main/java/org/springframework/samples/petclinic/api/application/VisitsServiceClient.java:31 VisitsServiceClient | docker-compose.yml:50 visits-service | ok | hostname = "http://visits-service/": real |
| spring-petclinic-microservices | data | spring-petclinic-customers-service/src/main/java/org/springframework/samples/petclinic/customers/model/PetType.java:27 PetType | spring-petclinic-customers-service/src/main/resources/db/mysql/schema.sql:5 types | ok | la entidad JPA tambien corresponde al schema de MySQL (las etiquetas solo usan HSQLDB) |
| spring-petclinic-microservices | data | spring-petclinic-vets-service/src/main/resources/db/mysql/data.sql:1 data.sql | spring-petclinic-vets-service/src/main/resources/db/mysql/schema.sql:12 specialties | ok | data.sql inserta en la tabla definida en schema.sql: real |
| spring-petclinic-microservices | data | spring-petclinic-customers-service/src/main/resources/db/hsqldb/data.sql:1 data.sql | spring-petclinic-customers-service/src/main/resources/db/hsqldb/schema.sql:5 types | ok | data.sql inserta en la tabla definida en schema.sql: real |
| spring-petclinic-microservices | service | docker-compose.yml:143 grafana-server | docker/grafana/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| spring-petclinic-microservices | data | spring-petclinic-vets-service/src/main/resources/db/hsqldb/data.sql:1 data.sql | spring-petclinic-vets-service/src/main/resources/db/hsqldb/schema.sql:5 vets | ok | data.sql inserta en la tabla definida en schema.sql: real |
| eShop | route | src/WebhookClient/Endpoints/AuthenticationEndpoints.cs:12 POST /logout | src/WebhookClient/Endpoints/AuthenticationEndpoints.cs:10 AuthenticationEndpoints.MapAuthenticationEndpoints | ok | MapPost("/logout") con lambda inline: ruta real de WebhookClient no etiquetada |
| eShop | route | src/Ordering.API/Program.cs:1 Program.cs | src/eShop.ServiceDefaults/Extensions.cs:108 Extensions.MapDefaultEndpoints | ok | MapDefaultEndpoints: montaje real |
| eShop | http | src/WebApp/Program.cs:1 Program.cs | src/Catalog.API/Apis/CatalogApi.cs:47 GET /api/catalog/items/:id/pic | ok | MapForwarder reenvía a /api/catalog/items/{id}/pic: flujo real |
| eShop | route | src/WebApp/Program.cs:32 ANY /product-images/:id | src/WebApp/Program.cs:1 Program.cs | ok | ruta MapForwarder declarada en el módulo |
| eShop | route | src/PaymentProcessor/Program.cs:1 Program.cs | src/eShop.ServiceDefaults/Extensions.cs:108 Extensions.MapDefaultEndpoints | ok | MapDefaultEndpoints: montaje real |
| eShop | data | src/Catalog.API/Infrastructure/EntityConfigurations/CatalogBrandEntityTypeConfiguration.cs:6 CatalogBrandEntityTypeConfiguration.Configure | src/Catalog.API/Infrastructure/Migrations/20231009153249_Initial.cs:29 CatalogBrand | ok | builder.ToTable("CatalogBrand") -> CreateTable de la migración: mapeo real |
| eShop | data | src/Catalog.API/Model/CatalogItem.cs:7 CatalogItem | src/Catalog.API/Infrastructure/Migrations/20231009153249_Initial.cs:53 Catalog | ok | entidad CatalogItem -> tabla Catalog (ToTable) de la migración: real |
| eShop | route | src/WebhookClient/Program.cs:1 Program.cs | src/WebhookClient/Endpoints/AuthenticationEndpoints.cs:10 AuthenticationEndpoints.MapAuthenticationEndpoints | ok | app.MapAuthenticationEndpoints(): montaje real |
| eShop | route | src/WebhookClient/Program.cs:1 Program.cs | src/WebhookClient/Endpoints/WebhookEndpoints.cs:8 WebhookEndpoints.MapWebhookEndpoints | ok | app.MapWebhookEndpoints(): montaje real |
| eShop | data | src/Catalog.API/Infrastructure/EntityConfigurations/CatalogItemEntityTypeConfiguration.cs:6 CatalogItemEntityTypeConfiguration.Configure | src/Catalog.API/Infrastructure/Migrations/20231009153249_Initial.cs:53 Catalog | ok | builder.ToTable("Catalog") -> migración: real |
| proshop_mern | route | backend/server.js:45 GET / | backend/server.js:1 server.js | ok | app.get("/") en server.js: ruta real no etiquetada |
| wild-workouts | service | docker-compose.yml:34 trainer-grpc | docker/app/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| wild-workouts | service | docker-compose.yml:14 trainer-http | .env:1 .env | ok | env_file: .env del servicio compose: real |
| wild-workouts | http | web/src/repositories/user.js:37 loginUser | api/openapi/users.yml:19 GET /api/users/current | ok | llamada real al endpoint (cliente, SDK generado o navegación) |
| wild-workouts | service | docker-compose.yml:123 firestore-component-tests | docker/firestore-emulator/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| wild-workouts | env | web/src/repositories/user.js:1 user.js | web/src/repositories/user.js:19 VUE_APP_USERS_HTTP_PORT | ok | process.env.VUE_APP_*: lectura real sin definicion en el repo |
| wild-workouts | rpc | internal/users/main.go:18 main | api/protobuf/users.proto:10 RPC users.UsersService/GetTrainingBalance | ok | RegisterUsersServiceServer: registro real |
| wild-workouts | service | docker-compose.yml:93 users-grpc | docker/app/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| wild-workouts | http | web/src/repositories/user.js:37 loginUser | internal/users/openapi_api.gen.go:166 GET /users/current | ok | loginUser llama a usersAPI.getCurrentUser del SDK generado: flujo real no etiquetado |
| wild-workouts | env | internal/common/server/http.go:62 addAuthMiddleware | internal/common/server/http.go:69 SERVICE_ACCOUNT_FILE | ok | os.Getenv("SERVICE_ACCOUNT_FILE"): lectura real sin definicion |
| wild-workouts | service | .env:1 .env | docker-compose.yml:113 firestore | ok | FIRESTORE_EMULATOR_HOST=firestore:8787 apunta al servicio compose firestore: cableado real |
| rails-realworld | data | app/models/comment.rb:1 Comment | db/migrate/20160712061113_create_comments.rb:3 comments | ok | la migracion create_table crea la misma tabla que db/schema.rb: relacion real |
| rails-realworld | data | app/models/favorite.rb:1 Favorite | db/migrate/20160712055201_create_favorites.rb:3 favorites | ok | la migracion create_table crea la misma tabla que db/schema.rb: relacion real |
| rails-realworld | data | app/models/follow.rb:1 Follow | db/migrate/20160712061614_acts_as_follower_migration.rb:3 follows | ok | la migracion create_table crea la misma tabla que db/schema.rb: relacion real |
| rails-realworld | data | app/models/article.rb:1 Article | db/migrate/20160712052128_create_articles.rb:3 articles | ok | la migracion create_table crea la misma tabla que db/schema.rb: relacion real |
| rails-realworld | data | app/models/user.rb:1 User | db/migrate/20160712045707_devise_create_users.rb:3 users | ok | la migracion create_table crea la misma tabla que db/schema.rb: relacion real |
| phoenix-realworld | route | lib/real_world_web/router.ex:35 PUT /user | lib/real_world_web/controllers/user_controller.ex:1 RealWorldWeb.UserController | ok | flujo real fuera del etiquetado |
| phoenix-realworld | route | lib/real_world_web/router.ex:24 ANY /comments | lib/real_world_web/controllers/comment_controller.ex:1 RealWorldWeb.CommentController | ok | flujo real fuera del etiquetado |
| phoenix-realworld | route | lib/real_world_web/router.ex:39 GET /profiles/:username | lib/real_world_web/controllers/profile_controller.ex:1 RealWorldWeb.ProfileController | ok | flujo real fuera del etiquetado |
| phoenix-realworld | route | lib/real_world_web/router.ex:36 POST /users | lib/real_world_web/controllers/user_controller.ex:1 RealWorldWeb.UserController | ok | flujo real fuera del etiquetado |
| phoenix-realworld | data | priv/repo/migrations/20171225141624_add_cascade_delete_to_favorites.exs:12 RealWorld.Repo.Migrations.AddCascadeDeleteToFavorites.down | priv/repo/migrations/20171020203610_create_favorites.exs:5 favorites | ok | la migración ejecuta ALTER/SQL sobre la tabla: real |
| phoenix-realworld | data | lib/real_world/blog/blog.ex:56 RealWorld.Blog.list_tags | priv/repo/migrations/20170426154053_create_blog_article.exs:5 articles | ok | SQL crudo "from articles" en list_tags: acceso real no etiquetado |
| phoenix-realworld | route | lib/real_world_web/router.ex:33 GET /tags | lib/real_world_web/controllers/tag_controller.ex:1 RealWorldWeb.TagController | ok | flujo real fuera del etiquetado |
| phoenix-realworld | route | lib/real_world_web/router.ex:31 DELETE /articles/:slug/favorite | lib/real_world_web/controllers/article_controller.ex:1 RealWorldWeb.ArticleController | ok | flujo real fuera del etiquetado |
| phoenix-realworld | data | lib/real_world/blog/blog.ex:56 RealWorld.Blog.list_tags | lib/real_world/blog/article.ex:1 RealWorld.Blog.Article | ok | SQL crudo "from articles" en list_tags: acceso real no etiquetado |
| phoenix-realworld | route | lib/real_world_web/router.ex:30 POST /articles/:slug/favorite | lib/real_world_web/controllers/article_controller.ex:1 RealWorldWeb.ArticleController | ok | ruta real; el handler cae en la clase controladora |
| kotlinconf-app | data | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/MigrationRunner.kt:105 MigrationRunner.appliedVersions | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/MigrationRunner.kt:19 SchemaMigrations | ok | MigrationRunner consulta la tabla Exposed SchemaMigrations: acceso real |
| kotlinconf-app | data | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/MigrationRunner.kt:66 MigrationRunner.currentVersion | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/MigrationRunner.kt:19 SchemaMigrations | ok | MigrationRunner consulta la tabla Exposed SchemaMigrations: acceso real |
| kotlinconf-app | data | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/MigrationRunner.kt:29 MigrationRunner.migrate | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/MigrationRunner.kt:19 SchemaMigrations | ok | MigrationRunner consulta la tabla Exposed SchemaMigrations: acceso real |
| kotlinconf-app | data | backend/src/main/resources/db/migrations/V004__add_year_and_signed_policies_again.sql:1 V004__add_year_and_signed_policies_again.sql | backend/src/main/resources/db/migrations/V001__initial_schema.sql:4 Users | ok | DML (UPDATE/INSERT ... SELECT) de una migración Flyway posterior sobre la tabla creada en V001: real |
| kotlinconf-app | data | backend/src/main/kotlin/org/jetbrains/kotlinconf/backend/schema/SignedPolicies.kt:9 SignedPolicies | backend/src/main/resources/db/migrations/V004__add_year_and_signed_policies_again.sql:13 SignedPolicies | ok | la migracion V004 vuelve a crear SignedPolicies: el modelo mapea tambien esa tabla |
| kotlinconf-app | data | backend/src/main/resources/db/migrations/V002__add_year_and_signed_policies.sql:1 V002__add_year_and_signed_policies.sql | backend/src/main/resources/db/migrations/V001__initial_schema.sql:12 Votes | ok | DML (UPDATE/INSERT ... SELECT) de una migración Flyway posterior sobre la tabla creada en V001: real |
| kotlinconf-app | data | backend/src/main/resources/db/migrations/V002__add_year_and_signed_policies.sql:1 V002__add_year_and_signed_policies.sql | backend/src/main/resources/db/migrations/V001__initial_schema.sql:23 Feedback | ok | DML (UPDATE/INSERT ... SELECT) de una migración Flyway posterior sobre la tabla creada en V001: real |
| kotlinconf-app | data | backend/src/main/resources/db/migrations/V004__add_year_and_signed_policies_again.sql:1 V004__add_year_and_signed_policies_again.sql | backend/src/main/resources/db/migrations/V001__initial_schema.sql:23 Feedback | ok | DML (UPDATE/INSERT ... SELECT) de una migración Flyway posterior sobre la tabla creada en V001: real |
| kotlinconf-app | data | backend/src/main/resources/db/migrations/V002__add_year_and_signed_policies.sql:1 V002__add_year_and_signed_policies.sql | backend/src/main/resources/db/migrations/V001__initial_schema.sql:4 Users | ok | DML (UPDATE/INSERT ... SELECT) de una migración Flyway posterior sobre la tabla creada en V001: real |
| kotlinconf-app | data | backend/src/main/resources/db/migrations/V004__add_year_and_signed_policies_again.sql:1 V004__add_year_and_signed_policies_again.sql | backend/src/main/resources/db/migrations/V001__initial_schema.sql:12 Votes | ok | DML (UPDATE/INSERT ... SELECT) de una migración Flyway posterior sobre la tabla creada en V001: real |
| ghostfolio | env | apps/api/src/app/endpoints/mcp/mcp.module.ts:1 mcp.module.ts | apps/api/src/environments/environment.prod.ts:29 version | ok | lectura de la configuración del módulo environment |
| ghostfolio | env | apps/api/src/app/user/user.service.ts:279 UserService.user | apps/api/src/environments/environment.prod.ts:27 production | ok | lectura de la configuración del módulo environment |
| ghostfolio | env | apps/api/src/services/configuration/configuration.service.ts:45 ConfigurationService.constructor | apps/api/src/services/configuration/configuration.service.ts:56 CACHE_QUOTES_TTL | ok | clave de cleanEnv(process.env, {...}): lectura real |
| ghostfolio | env | apps/api/src/services/configuration/configuration.service.ts:45 ConfigurationService.constructor | apps/api/src/services/configuration/configuration.service.ts:86 GOOGLE_CLIENT_ID | ok | cleanEnv: lectura real |
| ghostfolio | env | apps/api/src/services/queues/data-gathering/data-gathering.processor.ts:31 DataGatheringProcessor | apps/api/src/services/configuration/configuration.service.ts:119 PROCESSOR_GATHER_ASSET_PROFILE_CONCURRENCY | ok | process.env.PROCESSOR_GATHER_ASSET_PROFILE_CONCURRENCY: lectura real |
| ghostfolio | env | apps/api/src/services/configuration/configuration.service.ts:45 ConfigurationService.constructor | apps/api/src/services/configuration/configuration.service.ts:49 API_KEY_BETTER_UPTIME | ok | cleanEnv: lectura real |
| ghostfolio | env | apps/api/src/services/configuration/configuration.service.ts:45 ConfigurationService.constructor | apps/api/src/services/configuration/configuration.service.ts:48 API_KEY_ALPHA_VANTAGE | ok | cleanEnv: lectura real |
| ghostfolio | env | apps/api/src/services/configuration/configuration.service.ts:45 ConfigurationService.constructor | apps/api/src/services/configuration/configuration.service.ts:103 OIDC_CLIENT_SECRET | ok | cleanEnv: lectura real |
| ghostfolio | env | apps/api/src/middlewares/html-template.middleware.ts:131 HtmlTemplateMiddleware.use | apps/api/src/main.ts:150 ROOT_URL | ok | process.env.ROOT_URL: lectura real |
| ghostfolio | data | prisma/migrations/20230215174320_changed_data_source_from_ghostfolio_to_manual/migration.sql:1 migration.sql | prisma/migrations/20210605161257_added_symbol_profile/migration.sql:5 SymbolProfile | ok | UPDATE "SymbolProfile" en una migración posterior: acceso real |
| django-react-blog | service | frontend/src/components/Login.js:9 LoginForm.render | docker-compose-dm.yml:19 backend | ok | EmailSignInForm endpoint="http://localhost:8000/...": el frontend llama al backend publicado en el puerto 8000 |
| django-react-blog | service | docker-compose.yml:53 nginx_proxy | nginx_proxy/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| django-react-blog | env | backend/backend/wsgi.py:1 wsgi.py | backend/backend/wsgi.py:14 DJANGO_SETTINGS_MODULE | ok | os.environ.setdefault("DJANGO_SETTINGS_MODULE"): lectura/escritura real |
| django-react-blog | service | docker-compose.yml:37 frontend | frontend/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| django-react-blog | env | backend/manage.py:1 manage.py | backend/backend/wsgi.py:14 DJANGO_SETTINGS_MODULE | ok | os.environ.setdefault("DJANGO_SETTINGS_MODULE"): lectura real |
| django-react-blog | data | backend/posts/models.py:12 unique_slug | backend/posts/models.py:26 Post | ok | Post.objects.filter(...) en unique_slug: acceso real |
| django-react-blog | http | frontend/src/actions/auth.js:9 signinUser | backend/backend/urls.py:29 ANY /api/v1/auth | ok | axios.post(`${ROOT_URL}/auth/`) -> obtain_auth_token: llamada real (handler de librería, omitido en etiquetas) |
| django-react-blog | service | docker-compose.yml:15 backend | backend/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| go-coffeeshop | route | internal/counter/app/router/counter_grpc_server.go:31 NewGRPCCounterServer | internal/counter/app/router/counter_grpc_server.go:21 counterGRPCServer | ok | RegisterCounterServiceServer(grpcServer, &svc): registro real |
| go-coffeeshop | env | pkg/config/configs.go:4 App | pkg/config/configs.go:6 APP_VERSION | ok | tag env:"APP_VERSION": lectura real |
| go-coffeeshop | data | internal/barista/infras/postgresql/query.sql.go:1 query.sql.go | db/migrations/000002_init_baristadb.up.sql:23 barista_orders | ok | consulta generada por sqlc sobre barista.barista_orders: real |
| go-coffeeshop | env | pkg/config/configs.go:14 Log | pkg/config/configs.go:15 LOG_LEVEL | ok | tag env:"LOG_LEVEL": lectura real |
| go-coffeeshop | data | internal/counter/infras/postgresql/query.sql.go:1 query.sql.go | internal/counter/infras/postgresql/models.go:14 OrderLineItem | ok | consulta generada sobre "order".line_items -> struct sqlc OrderLineItem: real |
| go-coffeeshop | service | cmd/web/app/js/script.js:1 initApp | docker-compose.yaml:52 product | fp | url: 'http://localhost:5001' es un valor por defecto que se sustituye por la URL del proxy; no es una llamada real al servicio product |
| go-coffeeshop | route | internal/product/app/router/product_grpc_server.go:24 NewProductGRPCServer | internal/product/app/router/product_grpc_server.go:19 productGRPCServer | ok | RegisterProductServiceServer: registro real |
| go-coffeeshop | data | internal/counter/infras/postgresql/query/query.sql:17 GetByID | db/migrations/000001_init_counterdb.up.sql:35 line_items | ok | consulta sqlc GetByID hace JOIN con line_items: real |
| go-coffeeshop | env | cmd/counter/config/config.go:22 PG | cmd/barista/config/config.go:22 PG_POOL_MAX | ok | tag env:"PG_POOL_MAX": lectura real |
| go-coffeeshop | data | internal/kitchen/infras/postgresql/query.sql.go:1 query.sql.go | db/migrations/000003_init_kitchendb.up.sql:23 kitchen_orders | ok | consulta generada por sqlc sobre kitchen.kitchen_orders: real |
| sb3-course | service | k8s/manifests/applications/inventory-service.yml:2 Deployment/inventory-service | k8s/manifests/infra/loki.yml:23 Service/loki | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/applications/inventory-service.yml:48 ConfigMap/inventory-service-config | k8s/manifests/infra/mysql.yml:42 Service/mysql | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/infra/kafka.yml:2 Deployment/broker | k8s/manifests/infra/zookeeper.yml:33 Service/zookeeper | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/infrastructure/kafka-ui.yml:2 Deployment/kafka-ui | k8s/manifests/infrastructure/kafka.yml:50 Service/broker | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/applications/common-config.yml:3 ConfigMap/common-config | k8s/manifests/infra/kafka.yml:50 Service/broker | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/infrastructure/prometheus.yml:44 ConfigMap/prometheus-configmap | k8s/manifests/applications/api-gateway.yml:53 Service/api-gateway | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/infra/kafka.yml:67 ConfigMap/kafka-config | k8s/manifests/infra/zookeeper.yml:33 Service/zookeeper | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| sb3-course | service | k8s/manifests/infrastructure/mysql.yaml:2 Deployment/mysql | k8s/manifests/infrastructure/mysql.yaml:88 ConfigMap/mysql-initdb-config | ok | flujo real fuera del etiquetado |
| sb3-course | service | k8s/manifests/infra/tempo.yml:39 Service/tempo | k8s/manifests/infra/tempo.yml:2 Deployment/tempo | ok | flujo real fuera del etiquetado |
| sb3-course | service | k8s/manifests/applications/notification-service.yml:53 ConfigMap/notification-service-config | k8s/manifests/infrastructure/schema-registry.yml:30 Service/schema-registry | ok | referencia en manifiesto k8s (URL *.svc o configMapKeyRef) al Service: cableado real |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/user/user.schema.dart:40 _UserRepository.insert | server/packages/db/lib/src/models/user/user.schema.dart:27 users | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/post/post.schema.dart:56 _PostRepository.update | server/packages/db/lib/src/models/post/post.dart:5 Post | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/story/story.schema.dart:56 _StoryRepository.update | server/packages/db/lib/src/models/story/story.schema.dart:27 stories | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/comment/comment.schema.dart:55 _CommentRepository.update | server/packages/db/lib/src/models/comment/comment.dart:5 Comment | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/user/user.schema.dart:56 _UserRepository.update | server/packages/db/lib/src/models/user/user.schema.dart:27 users | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/user/user.schema.dart:40 _UserRepository.insert | server/packages/db/lib/src/models/user/user.dart:5 User | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/post/post.schema.dart:40 _PostRepository.insert | server/packages/db/lib/src/models/post/post.schema.dart:27 posts | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/user/user.schema.dart:56 _UserRepository.update | server/packages/db/lib/src/models/user/user.dart:5 User | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/story/story.schema.dart:56 _StoryRepository.update | server/packages/db/lib/src/models/story/story.dart:6 Story | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| full-stack-flutter-app | data | server/packages/db/lib/src/models/comment/comment.schema.dart:40 _CommentRepository.insert | server/packages/db/lib/src/models/comment/comment.schema.dart:27 comments | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| aspire-samples | env | samples/aspire-with-javascript/AspireJavaScript.ServiceDefaults/Extensions.cs:70 Extensions.AddOpenTelemetryExporters | samples/Metrics/ServiceDefaults/Extensions.cs:72 OTEL_EXPORTER_OTLP_ENDPOINT | ok | Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"]: lectura real de entorno |
| aspire-samples | env | samples/polyglot-task-queue/worker-python/main.py:1 main.py | samples/container-build/ginapp/otel.go:53 OTEL_SERVICE_NAME | ok | os.environ.get(OTEL_SERVICE_NAME): lectura real |
| aspire-samples | route | samples/aspire-with-javascript/AspireJavaScript.MinimalApi/Program.cs:1 Program.cs | samples/aspire-with-javascript/AspireJavaScript.ServiceDefaults/Extensions.cs:91 Extensions.MapDefaultEndpoints | ok | app.MapDefaultEndpoints(): método de extensión del repo que mapea /health y /alive |
| aspire-samples | route | samples/aspire-shop/AspireShop.BasketService/Program.cs:1 Program.cs | samples/aspire-shop/AspireShop.BasketService/BasketService.cs:8 BasketService | ok | MapGrpcService<BasketService>(): registro real del servicio gRPC |
| aspire-samples | env | samples/polyglot-task-queue/frontend/vite.config.ts:1 vite.config.ts | samples/aspire-with-node/frontend/vite.config.ts:11 API_HTTPS | ok | process.env.API_HTTPS en vite.config: lectura real |
| aspire-samples | route | samples/aspire-shop/AspireShop.Frontend/Program.cs:1 Program.cs | samples/aspire-shop/AspireShop.ServiceDefaults/Extensions.cs:93 Extensions.MapDefaultEndpoints | ok | MapDefaultEndpoints: montaje real |
| aspire-samples | route | samples/aspire-shop/AspireShop.CatalogDbManager/Program.cs:1 Program.cs | samples/aspire-shop/AspireShop.ServiceDefaults/Extensions.cs:93 Extensions.MapDefaultEndpoints | ok | MapDefaultEndpoints: montaje real |
| aspire-samples | env | samples/polyglot-task-queue/worker-csharp/Extensions.cs:81 Extensions.AddOpenTelemetryExporters | samples/Metrics/ServiceDefaults/Extensions.cs:72 OTEL_EXPORTER_OTLP_ENDPOINT | ok | Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"]: lectura real |
| aspire-samples | route | samples/aspire-shop/AspireShop.CatalogService/Program.cs:1 Program.cs | samples/aspire-shop/AspireShop.ServiceDefaults/Extensions.cs:93 Extensions.MapDefaultEndpoints | ok | MapDefaultEndpoints: montaje real |
| aspire-samples | env | samples/vite-csharp-postgres/frontend/vite.config.ts:1 vite.config.ts | samples/aspire-with-node/frontend/vite.config.ts:11 API_HTTP | ok | process.env.API_HTTP en vite.config: lectura real |
| 8mb.local | env | backend-api/app/celery_app.py:1 celery_app.py | .env.example:44 REDIS_URL | ok | flujo real fuera del etiquetado |
| 8mb.local | env | backend-api/app/routers/system.py:93 api_version | Dockerfile:125 APP_VERSION | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| 8mb.local | env | backend-api/app/settings_manager.py:311 update_auth_settings | .env.example:13 AUTH_USER | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| 8mb.local | env | worker/app/tasks.py:93 _encode_gate | .github/workflows/test.yml:43 LOCAL_RUNTIME | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| 8mb.local | env | worker/app/hw_detect.py:77 _append_vaapi_driver_paths | Dockerfile:217 LIBVA_DRIVERS_PATH | ok | flujo real fuera del etiquetado |
| 8mb.local | env | worker/app/hw_detect.py:631 _hardware_mapping | worker/app/hw_detect.py:648 QSV_DEVICE | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| 8mb.local | env | backend-api/app/deps.py:1 deps.py | backend-api/app/config.py:51 BATCH_METADATA_TTL_HOURS | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| 8mb.local | env | backend-api/app/settings_manager.py:351 initialize_env_if_missing | .env.example:17 FILE_RETENTION_HOURS | ok | flujo real fuera del etiquetado |
| 8mb.local | env | backend-api/app/deps.py:93 _windows_memory_upload_limit_bytes | .env.example:23 MEDIA_MEMORY_LIMIT_GB | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| 8mb.local | route | backend-api/app/main.py:200 GET /:full_path | backend-api/app/main.py:201 serve_spa | ok | flujo real fuera del etiquetado |
| tchatchers | data | tchatchers_core/src/report.rs:119 Report.message | tchatchers_back/migrations/20230102170032_messages.up.sql:1 MESSAGE | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| tchatchers | data | tchatchers_back/migrations/20230717165058_add_persist_messages_queue.up.sql:1 20230717165058_add_persist_messages_queue.up.sql | tchatchers_back/migrations/20230715151704_change_process_table.up.sql:2 PROCESS_KIND | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | data | tchatchers_back/migrations/20230518163723_report_message_translation.up.sql:1 20230518163723_report_message_translation.up.sql | tchatchers_back/migrations/20230103190641_translations.up.sql:24 TRANSLATION | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | data | tchatchers_back/migrations/20230120221433_translations.up.sql:1 20230120221433_translations.up.sql | tchatchers_back/migrations/20230103190641_translations.up.sql:18 LABEL | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | env | tchatchers_back/src/main.rs:74 main | tchatchers_back/src/main.rs:78 TOWER_LOG | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| tchatchers | data | tchatchers_back/migrations/20230717193223_add_clean_rooms_queue.up.sql:1 20230717193223_add_clean_rooms_queue.up.sql | tchatchers_back/migrations/20230715151704_change_process_table.up.sql:2 PROCESS_KIND | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | data | tchatchers_back/migrations/20230702112232_deleted_records.up.sql:28 chatters_delete_trigger | tchatchers_back/migrations/20220829174521_create_tables.up.sql:1 CHATTER | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | data | tchatchers_back/migrations/20230120221433_translations.down.sql:1 20230120221433_translations.down.sql | tchatchers_back/migrations/20230103190641_translations.up.sql:24 TRANSLATION | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | data | tchatchers_back/migrations/20230109173206_update_ts_on_chatter.up.sql:5 update_lastupdated_timestamp | tchatchers_back/migrations/20220829174521_create_tables.up.sql:1 CHATTER | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| tchatchers | data | tchatchers_back/migrations/20230409175458_fix_typo.up.sql:1 20230409175458_fix_typo.up.sql | tchatchers_back/migrations/20230103190641_translations.up.sql:18 LABEL | ok | el script SQL (seed/migración/trigger) lee o escribe la tabla creada antes: real |
| NotyKT | env | noty-api/application/src/main/kotlin/dev/shreyaspatil/noty/api/di/module/ConfigModule.kt:33 ConfigModule.databaseConfig | noty-api/.env:2 PORT | fp | dbConfig.property("port") lee database.port (PGPORT); el enlace relajado a PORT es falso |
| NotyKT | data | noty-api/data/src/main/kotlin/dev/shreyaspatil/noty/data/dao/NoteDao.kt:42 NoteDaoImpl.add | noty-api/data/src/main/kotlin/dev/shreyaspatil/noty/data/entity/EntityUser.kt:25 EntityUser | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| NotyKT | service | noty-api/docker-compose.yml:4 app | noty-api/Dockerfile:1 Dockerfile | ok | flujo real fuera del etiquetado |
| terminus | route | config/routes.rb:113 GET /designs/:id | app/actions/designs/show.rb:7 Show | ok | ruta HTML de Hanami fuera del alcance etiquetado; handler correcto |
| terminus | route | config/routes.rb:217 POST /screens | app/actions/screens/create.rb:7 Create | ok | ruta HTML de Hanami fuera del alcance etiquetado; handler correcto |
| terminus | route | config/routes.rb:161 GET /extensions/:extension_id/sources | app/actions/extensions/sources/index.rb:8 Index | ok | ruta HTML de Hanami fuera del alcance etiquetado; handler correcto |
| terminus | route | config/routes.rb:104 GET /devices/:id/edit | app/actions/devices/edit.rb:7 Edit | ok | ruta HTML de Hanami fuera del alcance etiquetado; handler correcto |
| terminus | route | config/routes.rb:218 GET /screens/:id/edit | app/actions/screens/edit.rb:7 Edit | ok | ruta HTML de Hanami fuera del alcance etiquetado; handler correcto |
| terminus | data | config/db/migrate/20260106144016_alter_firmware_kind.rb:1 20260106144016_alter_firmware_kind.rb | app/relations/firmware.rb:6 Firmware | ok | la migración ejecuta ALTER/SQL sobre la tabla: real |
| terminus | env | config/settings.rb:7 Settings | app/aspects/designs/exporter.rb:28 GIT_TAG | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| terminus | env | config/settings.rb:7 Settings | config/settings.rb:30 HTTP_TIMEOUT_READ | ok | lectura real de la variable (os.getenv / campo de settings leído como settings.X); definición vista en .env, compose, Dockerfile, CI o el propio settings |
| terminus | route | config/routes.rb:32 GET / | app/actions/dashboard/show.rb:7 Show | ok | ruta HTML de Hanami fuera del alcance etiquetado; handler correcto |
| terminus | route | config/routes.rb:106 DELETE /devices/:id | app/actions/devices/delete.rb:7 Delete | ok | flujo real fuera del etiquetado |
| quarkus-super-heroes | service | rest-heroes/src/main/kubernetes/common.yml:3 ConfigMap/rest-heroes-config | rest-heroes/src/main/kubernetes/common.yml:119 Service/heroes-db | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| quarkus-super-heroes | service | rest-fights/src/main/kubernetes/openshift.yml:3 ConfigMap/rest-fights-config | rest-fights/src/main/kubernetes/common.yml:117 Service/fights-db | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| quarkus-super-heroes | service | grpc-locations/src/main/kubernetes/common.yml:3 ConfigMap/grpc-locations-config | grpc-locations/src/main/kubernetes/common.yml:126 Service/locations-db | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| quarkus-super-heroes | service | deploy/docker-compose/java25.yml:179 rest-narration-java25 | deploy/docker-compose/monitoring.yml:3 otel-lgtm | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| quarkus-super-heroes | service | deploy/docker-compose/java25.yml:49 rest-fights-java25 | deploy/docker-compose/monitoring.yml:3 otel-lgtm | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| quarkus-super-heroes | http | rest-fights/src/main/java/io/quarkus/sample/superheroes/fight/client/HeroClient.java:50 HeroClient.helloHeroes | rest-heroes/src/main/resources/openapi/openapi.yml:116 GET /api/heroes/hello | ok | cliente real hacia el endpoint del spec OpenAPI (GET /api/heroes/hello) |
| quarkus-super-heroes | service | rest-fights/src/main/docker-compose/native.yml:2 rest-fights-native | rest-fights/src/main/docker-compose/infra.yml:14 apicurio | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| quarkus-super-heroes | data | rest-villains/src/main/java/io/quarkus/sample/superheroes/villain/service/VillainService.java:95 VillainService.partialUpdateVillain | rest-villains/src/main/java/io/quarkus/sample/superheroes/villain/Villain.java:20 Villain | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| quarkus-super-heroes | data | rest-villains/src/main/java/io/quarkus/sample/superheroes/villain/service/VillainService.java:84 VillainService.replaceVillain | rest-villains/src/main/java/io/quarkus/sample/superheroes/villain/Villain.java:20 Villain | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| quarkus-super-heroes | service | rest-fights/src/main/kubernetes/kubernetes.yml:3 ConfigMap/rest-fights-config | rest-fights/src/main/kubernetes/common.yml:117 Service/fights-db | ok | dependencia real: URL/host del servicio en env o ConfigMap, o depends_on entre fragmentos compose |
| papermark | data | app/(ee)/api/ai/chat/[chatId]/route.ts:15 GET | prisma/schema/schema.prisma:285 Chat | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | app/(ee)/api/workflows/route.ts:16 GET | prisma/schema/team.prisma:128 UserTeam | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | ee/features/dataroom-freeze/lib/trigger/dataroom-freeze-archive.ts:510 generateAuditLogsCsv | prisma/migrations/20230912150657_initialize/migration.sql:102 View | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | app/(ee)/api/workflows/[workflowId]/steps/route.ts:331 PUT | prisma/schema/team.prisma:128 UserTeam | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | app/(ee)/api/workflows/[workflowId]/steps/route.ts:331 PUT | prisma/schema/workflow.prisma:15 Workflow | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | ee/features/conversations/lib/trigger/conversation-message-notification.ts:14 sendConversationMessageNotificationTask | prisma/migrations/20250404000000_add_questions_answer_conversation/migration.sql:36 ConversationParticipant | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | ee/features/ai/lib/trigger/process-excel-for-ai.ts:1 process-excel-for-ai.ts | prisma/schema/document.prisma:47 DocumentVersion | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | app/(ee)/api/ai/chat/route.ts:360 GET | prisma/migrations/20230912150657_initialize/migration.sql:102 View | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | prisma/schema/dataroom.prisma:1 Dataroom | prisma/migrations/20240327102407_add_dataroom/migration.sql:15 Dataroom | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| papermark | data | ee/features/ai/lib/trigger/process-pdf-for-ai.ts:15 processPdfForAITask | prisma/migrations/20231013165123_create_document_version/migration.sql:2 DocumentVersion | ok | acceso real al modelo/tabla (prisma.x / ORM / SQL) dentro de la función |
| micronaut-microservices-poc | http | web-vue/src/components/Dashboard.vue:1 Dashboard.vue | agent-portal-gateway/src/main/java/pl/altkom/asc/lab/micronaut/poc/gateway/DashboardGatewayController.java:26 POST /api/dashboard/totalsales | ok | flujo real fuera del etiquetado |
| micronaut-microservices-poc | http | agent-portal-gateway/src/main/java/pl/altkom/asc/lab/micronaut/poc/gateway/client/v1/PolicyGatewayClient.java:36 PolicyGatewayClient.terminate | policy-service-api/src/main/java/pl/altkom/asc/lab/micronaut/poc/policy/service/api/v1/PolicyOperations.java:22 POST /policies/terminate | ok | flujo real fuera del etiquetado |
| micronaut-microservices-poc | data | pricing-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/pricing/commands/CalculatePriceHandler.java:25 CalculatePriceHandler.handle | pricing-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/pricing/domain/Tariff.java:14 Tariff | ok | flujo real fuera del etiquetado |
| micronaut-microservices-poc | data | dashboard-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/queries/gettotalsales/GetTotalSalesQueryHandler.java:21 GetTotalSalesQueryHandler.handle | policy-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/policy/domain/Policy.java:20 Policy | fp | PolicyRepository homónimo de otro servicio (dashboard usa Elasticsearch) |
| micronaut-microservices-poc | data | auth-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/auth/DataLoader.java:18 DataLoader.onApplicationEvent | auth-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/auth/InsuranceAgent.java:14 InsuranceAgent | ok | flujo real fuera del etiquetado |
| micronaut-microservices-poc | http | agent-portal-gateway/src/main/java/pl/altkom/asc/lab/micronaut/poc/gateway/client/v1/DashboardGatewayClient.java:30 DashboardGatewayClient.queryAgentsSales | dashboard-service-api/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/service/api/v1/DashboardOperations.java:20 POST /dashboard/agentssales | ok | flujo real fuera del etiquetado |
| micronaut-microservices-poc | service | docker-compose.yml:33 kafka_manager | scripts/infra.yml:28 kafkaserver | fp | el puerto localhost:2181 casa con el kafkaserver de otro fichero compose (scripts/infra.yml) en vez del de docker-compose.yml |
| micronaut-microservices-poc | data | payment-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/payment/domain/PolicyRegisteredListener.java:21 PolicyRegisteredListener.onPolicyRegistered | payment-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/payment/domain/PolicyAccount.java:23 PolicyAccount | ok | flujo real fuera del etiquetado |
| micronaut-microservices-poc | env | web-angular/src/environments/environment.ts:1 environment.ts | web-angular/src/environments/environment.ts:6 production | ok | definición de la clave en el módulo environment (Angular) |
| micronaut-microservices-poc | data | dashboard-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/init/DataLoader.java:57 DataLoader.savePolicies | policy-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/policy/domain/Policy.java:20 Policy | fp | entidad homónima de otro servicio (el dashboard indexa PolicyDocument en Elasticsearch) |
| redash | env | redash/settings/__init__.py:1 __init__.py | redash/settings/__init__.py:23 REDASH_PROXIES_COUNT | ok | flujo real fuera del etiquetado |
| redash | env | redash/settings/__init__.py:1 __init__.py | redash/settings/__init__.py:420 REDASH_PAGE_SIZE_OPTIONS | ok | flujo real fuera del etiquetado |
| redash | data | redash/authentication/__init__.py:165 jwt_token_load_user_from_request | redash/models/users.py:78 User | ok | flujo real fuera del etiquetado |
| redash | data | redash/handlers/groups.py:34 GroupResource.post | redash/models/users.py:246 Group | ok | flujo real fuera del etiquetado |
| redash | data | redash/handlers/groups.py:145 GroupDataSourceListResource.get | redash/models/__init__.py:112 DataSource | ok | flujo real fuera del etiquetado |
| redash | env | redash/settings/__init__.py:1 __init__.py | redash/settings/__init__.py:52 REDASH_SCHEMAS_REFRESH_SCHEDULE | ok | flujo real fuera del etiquetado |
| redash | env | redash/settings/__init__.py:1 __init__.py | redash/settings/__init__.py:120 REDASH_CONTENT_SECURITY_POLICY_REPORT_URI | ok | flujo real fuera del etiquetado |
| redash | event | redash/authentication/__init__.py:203 user_logged_in | redash/authentication/__init__.py:241 init_app | ok | flujo real: registro/emisión hacia el consumidor del mismo tema |
| redash | data | redash/handlers/permissions.py:75 ObjectPermissionsListResource.delete | redash/models/users.py:78 User | ok | flujo real fuera del etiquetado |
| redash | route | redash/handlers/api.py:161 DELETE /api/data_sources/:data_source_id | redash/handlers/data_sources.py:86 DataSourceResource.delete | ok | flujo real fuera del etiquetado |
| woodpecker | route | server/router/api.go:138 GET /api/repos/:repo_id/secrets | server/api/repo_secret.go:154 GetSecretList | ok | flujo real fuera del etiquetado |
| woodpecker | data | server/api/users.go:71 GetUser | server/model/user.go:31 User | ok | lee el usuario a través del store |
| woodpecker | rpc | server/rpc/serve.go:63 Serve | rpc/proto/woodpecker.proto:158 RPC proto.WoodpeckerAuth/Auth | ok | registro del servicio gRPC con todos sus métodos |
| woodpecker | http | web/src/lib/api/index.ts:421 WoodpeckerClient.deleteOrg | server/router/api.go:71 DELETE /api/orgs/:org_id | ok | flujo real fuera del etiquetado |
| woodpecker | route | server/router/api.go:59 GET /api/orgs | server/api/org.go:41 GetOrgs | ok | flujo real fuera del etiquetado |
| woodpecker | env | cmd/server/flags.go:1 flags.go | cmd/server/flags.go:127 WOODPECKER_GRPC_SECRET_FILE | ok | flujo real fuera del etiquetado |
| woodpecker | rpc | server/rpc/serve.go:63 Serve | rpc/proto/woodpecker.proto:33 RPC proto.Woodpecker/Update | ok | registro del servicio gRPC con todos sus métodos |
| woodpecker | http | web/src/lib/api/index.ts:65 WoodpeckerClient.getRepoPermissions | server/router/api.go:106 GET /api/repos/:repo_id/permissions | ok | flujo real fuera del etiquetado |
| woodpecker | http | web/src/lib/api/index.ts:185 WoodpeckerClient.getRegistryList | server/router/api.go:145 GET /api/repos/:repo_id/registries | ok | flujo real fuera del etiquetado |
| woodpecker | http | web/src/lib/api/index.ts:215 WoodpeckerClient.deleteOrgRegistry | server/router/api.go:83 DELETE /api/orgs/:org_id/registries/:registry | ok | flujo real fuera del etiquetado |
| plausible-analytics | route | lib/plausible_web/router.ex:567 POST /settings/team/force_2fa/enable | lib/plausible_web/controllers/settings_controller.ex:69 PlausibleWeb.SettingsController.enable_team_force_2fa | ok | flujo real fuera del etiquetado |
| plausible-analytics | route | lib/plausible_web/router.ex:230 GET /sso/saml/signin/:integration_id | extra/lib/plausible_web/controllers/sso_controller.ex:77 PlausibleWeb.SSOController.saml_signin | ok | flujo real fuera del etiquetado |
| plausible-analytics | data | priv/repo/migrations/20200323083536_add_create_site_emails.exs:5 create_site_emails | priv/repo/structure.sql:163 create_site_emails | ok | flujo real fuera del etiquetado |
| plausible-analytics | route | lib/plausible_web/router.ex:588 GET /sso/notice | extra/lib/plausible_web/controllers/sso_controller.ex:59 PlausibleWeb.SSOController.provision_notice | ok | flujo real fuera del etiquetado |
| plausible-analytics | route | lib/plausible_web/router.ex:277 DELETE /goals/:id | lib/plausible_web/plugins/api/controllers/goals.ex:1 PlausibleWeb.Plugins.API.Controllers.Goals | ok | flujo real fuera del etiquetado |
| plausible-analytics | route | lib/plausible_web/router.ex:475 POST /login | lib/plausible_web/controllers/auth_controller.ex:276 PlausibleWeb.AuthController.login | ok | flujo real fuera del etiquetado |
| plausible-analytics | env | config/runtime.exs:1 runtime.exs | config/runtime.exs:279 DATA_DIR | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| plausible-analytics | data | lib/plausible/imported/browser.ex:1 Plausible.Imported.Browser | priv/ingest_repo/structure.sql:248 imported_browsers | ok | flujo real fuera del etiquetado |
| plausible-analytics | data | lib/plausible/billing/billing.ex:29 Plausible.Billing.subscription_cancelled | lib/plausible/billing/subscription.ex:1 Plausible.Billing.Subscription | ok | flujo real fuera del etiquetado |
| plausible-analytics | data | lib/workers/send_check_stats_emails.ex:30 Plausible.Workers.SendCheckStatsEmails.eligible_for_check_stats_email? | lib/plausible/teams/membership.ex:1 Plausible.Teams.Membership | ok | flujo real fuera del etiquetado |
| outline | data | server/models/Collection.ts:957 Collection.archiveWithCtx | server/models/Document.ts:150 Document | ok | flujo real fuera del etiquetado |
| outline | event | app/components/WebsocketProvider.tsx:133 unauthorized | app/components/WebsocketProvider.tsx:113 useConnectionHandlers | ok | flujo real fuera del etiquetado |
| outline | data | server/models/Collection.ts:488 Collection.onAfterCreate | server/models/UserMembership.ts:37 UserMembership | ok | flujo real fuera del etiquetado |
| outline | event | server/queues/processors/WebsocketsProcessor.ts:42 WebsocketsProcessor.perform | app/components/WebsocketProvider.tsx:580 collections.add_group | ok | flujo real fuera del etiquetado |
| outline | env | server/models/Team.ts:292 Team.url | .claude/skills/verify-outline/scripts/verify-outline.sh:107 URL | ok | flujo real fuera del etiquetado |
| outline | event | server/queues/processors/WebsocketsProcessor.ts:42 WebsocketsProcessor.perform | app/components/WebsocketProvider.tsx:475 collections.delete | ok | flujo real fuera del etiquetado |
| outline | data | server/models/GroupMembership.ts:41 GroupMembership | server/models/GroupUser.ts:24 GroupUser | ok | flujo real fuera del etiquetado |
| outline | event | server/queues/processors/WebsocketsProcessor.ts:42 WebsocketsProcessor.perform | app/components/WebsocketProvider.tsx:768 userMemberships.update | ok | flujo real fuera del etiquetado |
| outline | env | server/models/helpers/SubscriptionHelper.ts:18 SubscriptionHelper.unsubscribeUrl | .claude/skills/verify-outline/scripts/verify-outline.sh:107 URL | ok | flujo real fuera del etiquetado |
| outline | http | app/stores/DocumentsStore.ts:784 DocumentsStore.emptyTrash | server/routes/api/documents/documents.ts:2285 POST /api/documents.empty_trash | ok | flujo real fuera del etiquetado |
| karakeep | data | apps/workers/workers/crawlerWorker.ts:330 runCrawler | packages/db/schema.ts:44 users | ok | flujo real fuera del etiquetado |
| karakeep | data | packages/trpc/models/lists.ts:85 List.fromId | packages/db/schema.ts:543 bookmarkLists | ok | flujo real fuera del etiquetado |
| karakeep | data | packages/trpc/routers/bookmarks.ts:131 attemptToDedupLink | packages/db/schema.ts:236 bookmarks | ok | flujo real fuera del etiquetado |
| karakeep | data | apps/workers/workers/importWorker.ts:379 ImportWorker.processOneBookmark | packages/db/schema.ts:1031 importStagingBookmarks | ok | flujo real fuera del etiquetado |
| karakeep | route | packages/trpc/routers/admin.ts:607 MUTATION /trpc/admin/resetPassword | packages/trpc/routers/admin.ts:1 admin.ts | ok | flujo real fuera del etiquetado |
| karakeep | route | packages/trpc/routers/users.ts:104 QUERY /trpc/users/settings | packages/trpc/routers/users.ts:1 users.ts | ok | flujo real fuera del etiquetado |
| karakeep | event | packages/trpc/models/tags.ts:306 Tag.delete | apps/workers/workers/searchWorker.ts:30 SearchIndexingQueue | ok | flujo real fuera del etiquetado |
| karakeep | route | packages/trpc/routers/assets.ts:72 MUTATION /trpc/assets/detachAsset | packages/trpc/routers/assets.ts:1 assets.ts | ok | flujo real fuera del etiquetado |
| karakeep | route | packages/trpc/routers/webhooks.ts:74 QUERY /trpc/webhooks/list | packages/trpc/routers/webhooks.ts:1 webhooks.ts | ok | flujo real fuera del etiquetado |
| karakeep | env | packages/shared/config.ts:296 serverConfigSchema | .env.sample:3 NEXTAUTH_SECRET | ok | flujo real fuera del etiquetado |
| Kavita | route | Kavita.Server/Controllers/CollectionController.cs:258 DELETE /api/Collection | Kavita.Server/Controllers/CollectionController.cs:260 CollectionController.DeleteTag | ok | flujo real fuera del etiquetado |
| Kavita | data | Kavita.Database/DataContext.cs:112 DataContext.OnModelCreating | Kavita.Models/Entities/Chapter.cs:13 Chapter | ok | flujo real fuera del etiquetado |
| Kavita | route | Kavita.Server/Controllers/CollectionController.cs:303 POST /api/Collection/import-stack | Kavita.Server/Controllers/CollectionController.cs:305 CollectionController.ImportMalStack | ok | flujo real fuera del etiquetado |
| Kavita | event | Kavita.Server/Controllers/ReaderController.cs:862 ReaderController.BookmarkPage | Kavita.Services/CacheService.cs:347 CacheService.CleanupBookmarkCache | ok | flujo real fuera del etiquetado |
| Kavita | route | Kavita.Server/Controllers/CollectionController.cs:227 POST /api/Collection/update-series | Kavita.Server/Controllers/CollectionController.cs:229 CollectionController.RemoveTagFromMultipleSeries | ok | flujo real fuera del etiquetado |
| Kavita | data | Kavita.Models/Entities/History/KavitaPlusAuditLog.cs:13 KavitaPlusAuditLog | Kavita.Models/Entities/User/AppUser.cs:16 AppUser | ok | flujo real fuera del etiquetado |
| Kavita | http | UI/Web/src/app/_services/theme.service.ts:113 ThemeService.uploadTheme | Kavita.Server/Controllers/ThemeController.cs:121 POST /api/Theme/upload-theme | ok | flujo real fuera del etiquetado |
| Kavita | route | Kavita.Server/Controllers/StreamController.cs:70 POST /api/Stream/update-external-source | Kavita.Server/Controllers/StreamController.cs:72 StreamController.UpdateExternalSource | ok | flujo real fuera del etiquetado |
| Kavita | route | Kavita.Server/Controllers/CBLController.cs:84 POST /api/Cbl/upload-cbl-file | Kavita.Server/Controllers/CBLController.cs:86 CblController.SaveCblFromUrl | ok | flujo real fuera del etiquetado |
| Kavita | data | Kavita.Server/Controllers/SeriesController.cs:177 SeriesController.UpdateSeries | Kavita.Models/Entities/Library.cs:9 Library | ok | carga la biblioteca de la serie (Include de la navegación Library) |
| gotify | data | database/database.go:130 fillMissingSortKeys | model/application.go:10 Application | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| gotify | env | config/config.go:100 Get | gotify-server.env.example:347 NOCOLOR | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| gotify | route | router/router.go:145 GET /docs | docs/ui.go:71 UI | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| gotify | event | plugin/manager.go:57 NewManager | api/stream/stream.go:83 Notify | ok | flujo real: registro/emisión hacia el consumidor del mismo tema |
| gotify | event | router/router.go:28 Create | api/stream/stream.go:67 NotifyDeletedClient | ok | flujo real: registro/emisión hacia el consumidor del mismo tema |
| gotify | route | router/router.go:142 GET /swagger | docs/swagger.go:15 Serve | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| gotify | data | database/database.go:115 fillMissingCreatedAt | model/user.go:6 User | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| gotify | data | database/database.go:115 fillMissingCreatedAt | model/pluginconf.go:6 PluginConf | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| gotify | data | plugin/manager.go:372 Manager.initializeConfigurerForSingleUserPlugin | model/pluginconf.go:6 PluginConf | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| gotify | data | database/database.go:115 fillMissingCreatedAt | model/application.go:10 Application | ok | UPDATE real sobre el modelo (db.Model(new(model.X)) en un bucle de modelos) |
| docmost | data | apps/server/src/core/notification/services/page.notification.ts:427 PageNotificationService.getPageContext | apps/server/src/database/types/db.d.ts:430 Users | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| docmost | data | apps/server/src/core/notification/services/page.notification.ts:322 PageNotificationService.processDigest | apps/server/src/database/types/db.d.ts:313 Pages | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| docmost | data | apps/server/src/core/notification/services/verification.notification.ts:136 VerificationNotificationService.processVerificationExpired | apps/server/src/database/types/db.d.ts:636 PageVerifiers | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| docmost | http | apps/client/src/features/transclusion/services/transclusion-api.ts:7 lookupTransclusion | apps/server/src/core/page/transclusion/transclusion.controller.ts:23 POST /api/pages/transclusion/lookup | ok | llamada real al endpoint (cliente, SDK generado o navegación) |
| docmost | event | apps/server/src/core/notification/notification.service.ts:27 NotificationService.create | apps/client/src/features/notification/hooks/use-notification-socket.ts:18 notification | ok | flujo real: registro/emisión hacia el consumidor del mismo tema |
| docmost | data | apps/server/src/database/migrations/20260905T126412-integrations.ts:3 up | apps/server/src/database/migrations/20260905T126412-integrations.ts:32 integration_connections | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| docmost | data | apps/server/src/database/types/db.d.ts:476 Workspaces | apps/server/src/database/migrations/20240324T085500-workspaces.ts:6 workspaces | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| docmost | http | apps/client/src/features/transclusion/services/transclusion-api.ts:38 unsyncReference | apps/server/src/core/page/transclusion/transclusion.controller.ts:47 POST /api/pages/transclusion/unsync-reference | ok | llamada real al endpoint (cliente, SDK generado o navegación) |
| docmost | env | apps/server/src/integrations/environment/environment.service.ts:388 EnvironmentService.getIframeAllowedOrigins | .env.example:61 IFRAME_ALLOWED_ORIGINS | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| docmost | data | apps/server/src/core/notification/services/page.notification.ts:282 PageNotificationService.getEligiblePageUpdateUsers | apps/server/src/database/types/db.d.ts:430 Users | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| paperless-ngx | route | src/paperless/urls.py:81 POST /storage_paths/test | src/documents/views.py:4250 StoragePathViewSet.test | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| paperless-ngx | route | src/paperless/urls.py:82 GET /tasks/status_counts | src/documents/views.py:4668 TasksViewSet.status_counts | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| paperless-ngx | data | src/documents/views.py:4626 TasksViewSet.summary | src/documents/models.py:788 PaperlessTask | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| paperless-ngx | env | src/paperless/settings/__init__.py:1 __init__.py | src/paperless/settings/__init__.py:884 PAPERLESS_CONSUMER_BARCODE_RETAIN_SPLIT_PAGES | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| paperless-ngx | route | src/paperless/urls.py:81 PUT /storage_paths/:pk | src/documents/views.py:4206 StoragePathViewSet | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| paperless-ngx | env | src/paperless/settings/__init__.py:1 __init__.py | src/paperless/settings/__init__.py:1204 PAPERLESS_REMOTE_OCR_ALLOW_INTERNAL_ENDPOINTS | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| paperless-ngx | env | src/paperless/settings/custom.py:18 parse_hosting_settings | src/paperless/settings/custom.py:23 PAPERLESS_LOGOUT_REDIRECT_URL | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| paperless-ngx | env | src/paperless/settings/__init__.py:1 __init__.py | src/paperless/settings/__init__.py:1196 PAPERLESS_REMOTE_OCR_ENGINE | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| paperless-ngx | env | src/paperless/settings/__init__.py:1 __init__.py | src/paperless/settings/__init__.py:864 PAPERLESS_CONSUMER_ASN_BARCODE_PREFIX | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| paperless-ngx | env | src/paperless/settings/__init__.py:1 __init__.py | src/paperless/settings/__init__.py:1153 PAPERLESS_EMPTY_TRASH_DELAY | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| mastodon | http | app/javascript/mastodon/api/instance.ts:18 apiGetPrivacyPolicy | config/routes/api.rb:151 GET /api/v1/instance/privacy_policy | ok | llamada real al endpoint (cliente, SDK generado o navegación) |
| mastodon | data | app/models/trends/preview_card_provider_batch.rb:20 PreviewCardProviderBatch.preview_card_providers | app/models/preview_card_provider.rb:20 PreviewCardProvider | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| mastodon | env | config/initializers/paperclip.rb:1 paperclip.rb | app/lib/content_security_policy.rb:89 SWIFT_OBJECT_URL | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| mastodon | data | app/models/account_filter.rb:87 AccountFilter.status_scope | app/models/account.rb:65 Account | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| mastodon | env | app/models/backup.rb:18 Backup | app/models/backup.rb:21 S3_PERMISSION | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| mastodon | data | app/services/update_status_service.rb:85 UpdateStatusService.update_poll! | app/models/poll.rb:23 Poll | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| mastodon | data | app/controllers/api/v1/instances/domain_blocks_controller.rb:29 DomainBlocksController.show_domain_blocks_for_all? | app/models/setting.rb:43 Setting | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| mastodon | data | app/models/trends/status_batch.rb:28 StatusBatch.status_accounts | app/models/account.rb:65 Account | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| mastodon | data | app/controllers/api/v1/admin/tags_controller.rb:47 TagsController.set_tags | app/models/tag.rb:22 Tag | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| mastodon | data | lib/mastodon/cli/maintenance.rb:15 Poll | db/migrate/20190225031541_create_polls.rb:5 polls | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | route | src/api/core/organizations.rs:2988 PUT /organizations/:org_id/users/:user_id/reset-password-enrollment | src/api/core/organizations.rs:2989 put_reset_password_enrollment | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| vaultwarden | data | src/db/models/group.rs:261 Group.is_in_full_access_group | src/db/schema.rs:236 users_organizations | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | data | src/db/schema.rs:349 archives | migrations/mysql/2026-03-09-005927_add_archives/up.sql:3 archives | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | data | src/db/schema.rs:113 org_policies | migrations/postgresql/2020-03-13-205045_add_policy_table/up.sql:1 org_policies | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | data | src/db/models/collection.rs:676 CollectionUser.find_by_organization_and_user_uuid | src/db/schema.rs:226 users_collections | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | data | src/db/models/organization.rs:1147 OrganizationApiKey.save | src/db/schema.rs:251 organization_api_key | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | env | playwright/global-utils.ts:155 dbConfig | playwright/test.env:99 POSTGRES_PASSWORD | ok | lectura real de la variable (directa, por envoltorio o constante) o su definición en la plantilla |
| vaultwarden | data | src/db/models/collection.rs:342 Collection.find_by_uuid_and_user | src/db/schema.rs:38 collections | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | data | src/db/models/group.rs:498 GroupUser.find_by_group | src/db/schema.rs:300 groups | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| vaultwarden | data | src/db/schema.rs:62 event | migrations/postgresql/2022-10-18-170602_add_events/up.sql:1 event | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| dependency-track | event | apiserver/src/main/java/org/dependencytrack/dex/DexEngineInitializer.java:155 DexEngineInitializer.contextInitialized | apiserver/src/main/java/org/dependencytrack/vulnanalysis/InvokeVulnAnalyzerActivity.java:66 InvokeVulnAnalyzerActivity | ok | flujo real: registro/emisión hacia el consumidor del mismo tema |
| dependency-track | data | apiserver/src/main/java/org/dependencytrack/model/PolicyViolation.java:56 PolicyViolation | apiserver/src/main/java/org/dependencytrack/model/PolicyCondition.java:51 PolicyCondition | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| dependency-track | route | api/src/main/openapi/resources/extensions/extension-config.yaml:17 GET /api/v2/extension-points/:extension_point_name/extensions/:extension_name/config | apiserver/src/main/java/org/dependencytrack/resources/v2/ExtensionsResource.java:145 ExtensionsResource.getExtensionConfig | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| dependency-track | route | api/src/main/openapi/resources/extensions/extension-config.yaml:55 PUT /api/v2/extension-points/:extension_point_name/extensions/:extension_name/config | apiserver/src/main/java/org/dependencytrack/resources/v2/ExtensionsResource.java:176 ExtensionsResource.updateExtensionConfig | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| dependency-track | data | apiserver/src/main/java/org/dependencytrack/policy/cel/CelPolicyFunctions.java:259 CelPolicyFunctions.isExclusiveDependencyOf | apiserver/src/main/java/org/dependencytrack/model/Component.java:99 Component | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| dependency-track | data | apiserver/src/main/java/org/dependencytrack/notification/NotificationRuleContactsSupplier.java:42 NotificationRuleContactsSupplier.get | alpine/alpine-model/src/main/java/alpine/model/Team.java:64 Team | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| dependency-track | route | apiserver/src/main/java/org/dependencytrack/resources/v1/FindingResource.java:105 GET /v1/finding | apiserver/src/main/java/org/dependencytrack/resources/v1/FindingResource.java:417 FindingResource.getAllFindings | ok | ruta real servida por ese handler (fuera del scope etiquetado) |
| dependency-track | data | apiserver/src/main/java/org/dependencytrack/policy/cel/persistence/CelPolicyDao.java:364 CelPolicyDao.getApplicablePolicies | migration/src/main/resources/org/dependencytrack/migration/V202605022031__init.sql:1079 PROJECTS_TAGS | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| dependency-track | data | apiserver/src/main/java/org/dependencytrack/policy/vulnerability/VulnerabilityPolicyDao.java:565 VulnerabilityPolicyDao.listVulnPolicies | migration/src/main/resources/org/dependencytrack/migration/V202605022031__init.sql:1433 VULNERABILITY_POLICY | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| dependency-track | route | apiserver/src/main/java/org/dependencytrack/resources/v1/BomResource.java:155 GET /v1/bom/cyclonedx/project/:uuid | apiserver/src/main/java/org/dependencytrack/resources/v1/BomResource.java:191 BomResource.exportProjectAsCycloneDx | ok | ruta JAX-RS real (@GET + @Path) fuera del scope etiquetado |
| immich | data | mobile/lib/infrastructure/repositories/trashed_local_asset.repository.dart:276 TrashedLocalAssetRepository.getToTrash | mobile/lib/data/db/main/table/local/album_asset.dart:9 LocalAlbumAssetEntity | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| immich | http | packages/sdk/src/fetch-client.ts:4910 removeAssetEdits | open-api/immich-openapi-specs.json:4427 DELETE /api/assets/:id/edits | ok | llamada real al endpoint (cliente, SDK generado o navegación) |
| immich | data | server/src/schema/migrations/1744910873969-InitialMigration.ts:11 up | server/src/schema/migrations/1744910873969-InitialMigration.ts:139 assets_audit | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| immich | rpc | mobile/lib/domain/services/background_worker.service.dart:94 BackgroundWorkerBgService.init | mobile/ios/Runner/Background/BackgroundWorker.swift:127 BackgroundWorker.close | ok | llamada Dart al contrato Pigeon implementado en la plataforma nativa |
| immich | data | server/src/repositories/integrity.repository.ts:42 IntegrityRepository.getIntegrityReportSummary | server/src/schema/migrations/1781089983296-CreateIntegrityReportTable.ts:4 integrity_report | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| immich | data | server/src/repositories/access.repository.ts:514 ClusterGroupRequestAccess.checkGroupAccess | server/src/schema/migrations/1787148183729-ClusterGroups.ts:53 cluster_group_request | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| immich | data | server/src/repositories/shared-link.repository.ts:181 SharedLinkRepository.remove | server/src/schema/migrations/1744910873969-InitialMigration.ts:183 shared_links | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| immich | data | server/src/repositories/asset.repository.ts:753 AssetRepository.getTimeBuckets | server/src/schema/migrations/1744910873969-InitialMigration.ts:120 assets | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |
| immich | http | packages/sdk/src/fetch-client.ts:7334 updateAdminOnboarding | server/src/controllers/system-metadata.controller.ts:29 POST /api/system-metadata/admin-onboarding | ok | llamada real al endpoint (cliente, SDK generado o navegación) |
| immich | data | server/src/repositories/asset-edit.repository.ts:41 AssetEditRepository.getWithSyncInfo | server/src/schema/migrations/1768336671610-CreateAssetEditTable.ts:5 asset_edit | ok | acceso real a la tabla/modelo (consulta por nombre, modelo declarado o relación) |

## microservices-demo

Encontrados 92/93 · análisis 3.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | http · llamada no detectada | src/loadgenerator/locustfile.py:35 → src/frontend/handlers.go:59 (GET /) |

## full-stack-fastapi-template

Encontrados 114/115 · análisis 2.9 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | data · conectados por separado, sin camino | backend/app/api/routes/users.py:141 → backend/app/models.py:51 (table user (SQLModel User)) |

## koel

Encontrados 301/301 · análisis 28.8 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## spring-petclinic-microservices

Encontrados 82/83 · análisis 1.7 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | http · otro endpoint o endpoint sin handler | spring-petclinic-api-gateway/src/main/resources/static/scripts/pages/PetFormPage.js:61 → spring-petclinic-customers-service/src/main/java/org/springframework/samples/petclinic/customers/web/PetResource.java:57 (POST /api/customer/owners/{ownerId}/pets) |

## eShop

Encontrados 106/107 · análisis 11.5 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | route · ruta no detectada | src/Catalog.API/Apis/CatalogApi.cs:27 → src/Catalog.API/Apis/CatalogApi.cs:131 (GET /api/catalog/items (v2)) |

## proshop_mern

Encontrados 82/82 · análisis 0.7 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## wild-workouts

Encontrados 67/71 · análisis 2.5 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 4 | data · origen y destino sin aristas de flujo | internal/users/firestore.go:24 → internal/users/firestore.go:12 (collection users (Firestore))<br>internal/trainings/adapters/trainings_firestore_repository.go:44 → internal/trainings/adapters/trainings_firestore_repository.go:17 (collection trainings (Firestore))<br>internal/trainer/adapters/hour_firestore_repository.go:89 → internal/trainer/adapters/dates_firestore_repository.go:16 (collection trainer-hours (Firestore))<br>internal/trainer/adapters/dates_firestore_repository.go:42 → internal/trainer/adapters/dates_firestore_repository.go:16 (collection trainer-hours (Firestore)) |

## realworld-axum-sqlx

Encontrados 73/73 · análisis 0.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## rails-realworld

Encontrados 41/46 · análisis 0.4 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 5 | data · conectados por separado, sin camino | app/controllers/favorites_controller.rb:6 → app/models/favorite.rb:1 (ActiveRecord Favorite (table favorites))<br>app/controllers/favorites_controller.rb:12 → app/models/favorite.rb:1 (ActiveRecord Favorite (table favorites))<br>app/controllers/follows_controller.rb:7 → app/models/follow.rb:1 (ActiveRecord Follow (table follows))<br>app/controllers/follows_controller.rb:15 → app/models/follow.rb:1 (ActiveRecord Follow (table follows)) |

## phoenix-realworld

Encontrados 56/56 · análisis 0.5 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## kotlinconf-app

Encontrados 72/72 · análisis 10.8 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## ghostfolio

Encontrados 452/452 · análisis 28.1 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## django-react-blog

Encontrados 74/75 · análisis 1.5 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | service · origen sin aristas de flujo | frontend/src/actions/index.js:13 → nginx_proxy/nginx_proxy.conf:3 (frontend ROOT_URL http://api.<host>/api/v1 -> nginx api.* server block) |

## go-coffeeshop

Encontrados 82/86 · análisis 1.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 2 | event · conectados por separado, sin camino | internal/barista/eventhandlers/barista_ordered.go:73 → internal/counter/events/handlers/barista_order_updated.go:27 (event barista-order-updated (BaristaOrderUpdated))<br>internal/kitchen/eventhandlers/kitchen_ordered.go:77 → internal/counter/events/handlers/kitchen_order_updated.go:27 (event kitchen-order-updated (KitchenOrderUpdated)) |
| 2 | event · origen sin aristas de flujo | internal/counter/usecases/orders/service.go:69 → internal/barista/eventhandlers/barista_ordered.go:34 (event barista-order-created (BaristaOrdered))<br>internal/counter/usecases/orders/service.go:78 → internal/kitchen/eventhandlers/kitchen_ordered.go:37 (event kitchen-order-created (KitchenOrdered)) |

## sb3-course

Encontrados 90/90 · análisis 1.7 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## full-stack-flutter-app

Encontrados 95/95 · análisis 8.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## aspire-samples

Encontrados 115/117 · análisis 11.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | data · origen y destino sin aristas de flujo | samples/aspire-shop/AspireShop.CatalogDbManager/CatalogDbInitializer.cs:28 → samples/aspire-shop/AspireShop.CatalogDbManager/Migrations/20260709111930_Initial.cs:8 (catalogdb schema (MigrateAsync -> Initial migration)) |
| 1 | event · conectados por separado, sin camino | samples/polyglot-task-queue/worker-python/main.py:306 → samples/polyglot-task-queue/worker-python/main.py:174 (event queue tasks) |

## 8mb.local

Encontrados 154/154 · análisis 7.0 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## tchatchers

Encontrados 103/105 · análisis 1.8 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 2 | http · llamada no detectada | tchatchers_front/services/chat_service/src/service.rs:32 → tchatchers_back/src/ws.rs:56 (GET /ws/{room})<br>tchatchers_front/services/chat_service/src/lib.rs:33 → tchatchers_back/src/ws.rs:56 (GET /ws/{room}) |

## NotyKT

Encontrados 87/87 · análisis 5.8 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## terminus

Encontrados 122/122 · análisis 17.0 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## quarkus-super-heroes

Encontrados 138/139 · análisis 13.7 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | data · destino sin aristas de flujo | rest-fights/src/main/java/io/quarkus/sample/superheroes/fight/Fight.java:17 → deploy/db-init/initialize-database.js:6 (data Fights collection -> mongo init script (db fights)) |

## papermark

Encontrados 206/206 · análisis 32.7 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## micronaut-microservices-poc

Encontrados 115/123 · análisis 5.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 4 | data · origen y destino sin aristas de flujo | product-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/product/service/infrastructure/adapters/db/ProductsRepository.java:49 → product-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/product/service/domain/Product.java:16 (mongo collection product (Product document))<br>product-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/product/service/infrastructure/adapters/db/ProductsRepository.java:26 → product-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/product/service/domain/Product.java:16 (mongo collection product (write))<br>product-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/product/service/infrastructure/adapters/db/ProductsRepository.java:33 → product-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/product/service/domain/Product.java:16 (mongo collection product (read))<br>dashboard-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/infrastructure/adapters/elastic/PolicyElasticRepository.java:36 → dashboard-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/domain/PolicyDocument.java:14 (elastic index policy_stats (PolicyDocument)) |
| 2 | data · conectados por separado, sin camino | documents-service/src/main/kotlin/pl/altkom/asc/lab/micronaut/poc/documents/domain/PolicyRegisteredListener.kt:24 → documents-service/src/main/kotlin/pl/altkom/asc/lab/micronaut/poc/documents/domain/PolicyDocument.kt:10 (entity PolicyDocument (write))<br>documents-service/src/main/kotlin/pl/altkom/asc/lab/micronaut/poc/documents/infrastructure/adapters/web/DocumentsController.kt:18 → documents-service/src/main/kotlin/pl/altkom/asc/lab/micronaut/poc/documents/domain/PolicyDocument.kt:10 (entity PolicyDocument (read)) |
| 1 | data · destino sin aristas de flujo | dashboard-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/domain/PolicyRegisteredListener.java:17 → dashboard-service/src/main/java/pl/altkom/asc/lab/micronaut/poc/dashboard/domain/PolicyDocument.java:14 (elastic index policy_stats (write)) |
| 1 | service · conectados por separado, sin camino | docker-compose.yml:40 → docker-compose.yml:22 (kafka_manager ZK_HOSTS localhost:2181 -> kafkaserver) |

## redash

Encontrados 139/140 · análisis 21.6 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | http · otro endpoint o endpoint sin handler | client/app/services/widget.js:197 → redash/handlers/widgets.py:52 (POST /api/widgets/{widget_id}) |

## woodpecker

Encontrados 136/149 · análisis 42.4 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 9 | event · origen sin aristas de flujo | server/pipeline/cancel.go:90 → server/api/stream.go:108 (event pipeline events (pubsub))<br>server/pipeline/decline.go:67 → server/api/stream.go:108 (event pipeline events (pubsub))<br>server/pipeline/start.go:54 → server/api/stream.go:108 (event pipeline events (pubsub))<br>server/rpc/rpc.go:242 → server/api/stream.go:108 (event pipeline events (pubsub)) |
| 2 | event · origen y destino sin aristas de flujo | server/pipeline/start.go:43 → server/rpc/rpc.go:88 (event workflow task (queue))<br>server/scheduler/impl.go:149 → server/rpc/rpc.go:88 (event workflow task (queue)) |
| 1 | event · conectados por separado, sin camino | server/api/stream.go:107 → server/api/stream.go:108 (event pipeline events (pubsub)) |
| 1 | service · destino sin aristas de flujo | docker-compose.example.yaml:30 → cmd/server/grpc_server.go:36 (agent -> servidor gRPC (grpc-addr) del proceso server) |

## plausible-analytics

Encontrados 139/139 · análisis 44.9 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## outline

Encontrados 140/140 · análisis 36.8 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## karakeep

Encontrados 146/146 · análisis 32.7 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## Kavita

Encontrados 143/148 · análisis 196.9 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 2 | http · llamada no detectada | UI/Web/src/app/_services/review.service.ts:71 → Kavita.Server/Controllers/ReviewController.cs:159 (GET /api/review/all)<br>UI/Web/src/app/_services/font.service.ts:54 → Kavita.Server/Controllers/FontController.cs:50 (GET /api/font) |
| 1 | event · conectados por separado, sin camino | Kavita.Server/Controllers/CollectionController.cs:330 → Kavita.Services/Plus/SmartCollectionSyncService.cs:97 (event Sync (Hangfire)) |
| 1 | http · otro endpoint o endpoint sin handler | UI/Web/src/app/_services/theme.service.ts:117 → Kavita.Server/Controllers/ThemeController.cs:123 (POST /api/theme/upload-theme) |
| 1 | route · handler distinto | Kavita.Server/Controllers/ThemeController.cs:121 → Kavita.Server/Controllers/ThemeController.cs:123 (POST /api/theme/upload-theme) |

## gotify

Encontrados 120/120 · análisis 4.0 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## docmost

Encontrados 140/140 · análisis 25.9 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## paperless-ngx

Encontrados 193/193 · análisis 34.2 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## mastodon

Encontrados 190/190 · análisis 58.0 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|

## vaultwarden

Encontrados 173/174 · análisis 12.4 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 1 | event · conectados por separado, sin camino | src/api/core/accounts.rs:1788 → src/api/notifications.rs:560 (send_auth_response) |

## dependency-track

Encontrados 163/168 · análisis 117.1 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 3 | service · conectados por separado, sin camino | dev/compose.yaml:51 → dev/compose.yaml:47 (traefik router /api -> apiserver)<br>dev/compose.yaml:41 → dev/compose.yaml:35 (traefik router / -> frontend)<br>dev/compose.yaml:38 → dev/compose.yaml:20 (frontend API_BASE_URL -> traefik entrypoint 8080) |
| 2 | env · conectados por separado, sin camino | apiserver/src/main/java/org/dependencytrack/common/HttpClient.java:109 → apiserver/src/main/resources/application.properties:587 (dt.outbound.allowed-destinations)<br>apiserver/src/main/java/org/dependencytrack/common/HttpClient.java:312 → apiserver/src/main/resources/application.properties:587 (dt.outbound.allowed-destinations) |

## immich

Encontrados 247/254 · análisis 67.3 s

| n | patrón de falso negativo | ejemplos |
|---|---|---|
| 4 | service · origen y destino sin aristas de flujo | e2e/docker-compose.dev.yml:35 → e2e/docker-compose.dev.yml:9 (immich-server depends_on immich-init)<br>e2e/docker-compose.dev.yml:37 → e2e/docker-compose.dev.yml:56 (immich-server depends_on redis)<br>e2e/docker-compose.dev.yml:39 → e2e/docker-compose.dev.yml:62 (immich-server depends_on database)<br>e2e/docker-compose.dev.yml:52 → e2e/docker-compose.dev.yml:9 (immich-web depends_on immich-init) |
| 2 | service · conectados por separado, sin camino | server/src/repositories/config.repository.ts:199 → docker/docker-compose.yml:52 (default REDIS host redis)<br>server/src/repositories/config.repository.ts:233 → docker/docker-compose.yml:59 (default DB host database) |
| 1 | rpc · origen sin aristas de flujo | mobile/lib/domain/services/background_worker.service.dart:266 → mobile/android/app/src/main/kotlin/app/alextran/immich/sync/MessagesImplBase.kt:501 (pigeon MessagesImpl.cancelHashing) |
