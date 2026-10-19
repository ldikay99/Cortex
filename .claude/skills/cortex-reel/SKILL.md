---
name: cortex-reel
description: Produce a reel, demo video, GIF or screenshots of Córtex weaving a repository (weave speed, cinema mode, built-in WebM recorder, camera moves, showcase repos). Use when preparing marketing material, a README preview or a social post.
---

# Grabar un reel de Córtex

## Preparación

1. `docker compose up -d` y abre `http://localhost:8090` en Chrome, ventana 1920×1080 (pantalla completa con F11).
2. Analiza el repo antes de grabar para que no haya esperas: `docker exec cortex-analyzer cortex analyze <url>`. Luego ábrelo desde **Grafos guardados**.
3. Elige la velocidad del tejido en el botón `1×` (0.5×, 1×, 2×, 4×) o por URL: `http://localhost:8090/?velocidad=2`. Se recuerda entre sesiones.
4. En ese mismo panel activa **Entrar en modo cine al grabar** para ocultar la interfaz automáticamente.

## Grabar

- Botón ● de la barra: graba solo el canvas 3D a 60 fps en WebM (VP9 si está disponible). El chip `REC` muestra el tiempo; vuelve a pulsar para detener y descargar.
- <kbd>H</kbd> alterna el modo cine manualmente; <kbd>Esc</kbd> también sale.
- Para tomas con interfaz (panel de comunidades, búsqueda, fichas al pasar el ratón) usa una grabación de pantalla externa en lugar del grabador interno.

## Cámara

- <kbd>F</kbd>: la cámara persigue a la araña. Ideal para el arranque del tejido.
- Clic en una nebulosa: la araña viaja o salta hasta ella; la cámara la acompaña.
- Rueda: acercar o alejar despacio. Arrastre izquierdo gira, derecho desplaza; <kbd>W</kbd><kbd>A</kbd><kbd>S</kbd><kbd>D</kbd><kbd>Q</kbd><kbd>E</kbd> para movimientos suaves y constantes.
- Plano final: aléjate hasta ver todas las nebulosas y el nido latiendo en el centro.

## Guion de 50 s

| Tiempo | Toma |
| --- | --- |
| 0–6 s | Selector: pegar URL de GitHub, revisión de carpetas, **Tejer** |
| 6–20 s | <kbd>F</kbd> sigue a la araña tejiendo a 2× |
| 20–30 s | Alejar: nebulosas formándose, pulsos hacia el nido |
| 30–38 s | Panel de comunidades y búsqueda (<kbd>/</kbd>) de un símbolo |
| 38–45 s | Un agente pregunta por MCP «¿qué se rompe si cambio X?» |
| 45–50 s | Modo cine, plano amplio del universo completo |

## Repos públicos que lucen

- `https://github.com/fastapi/full-stack-fastapi-template`: Python + TypeScript, rutas y tablas, comunidades claras.
- `https://github.com/pallets/flask`: tamaño mediano, tejido rápido y legible.
- `https://github.com/tiangolo/sqlmodel`: buenas relaciones de herencia y documentación.
- `https://github.com/vercel/next.js` (con exclusiones en la revisión): universo enorme para el plano final.

Para mostrar versiones: analiza, cambia algo en el repo, vuelve a analizar; los nodos nuevos brillan en verde menta y los modificados en ámbar.

## Postproducción

- GIF de 8 s a 960 px: `ffmpeg -i reel.webm -vf "fps=15,scale=960:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" docs/media/preview.gif`
- MP4 para redes: `ffmpeg -i reel.webm -c:v libx264 -pix_fmt yuv420p -crf 18 docs/media/demo.mp4`
- Capturas a 1920×1080 en `docs/media/` con nombres descriptivos (`tejiendo.png`, `universo.png`, `nido.png`…).

— Creado por Jonathan C (ldikay99) · Colombia
