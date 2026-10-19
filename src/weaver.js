import * as THREE from 'three';

const HEADS = new Set(['module', 'doc']);
const LOOSE_MAX = 240;

export function createWeaver({ cosmos, spider, speed = 1, onHop, onProgress }) {
  const groups = [];
  const regionOf = new Map();
  const known = new Map();
  const pending = [];
  const late = [];
  const seenNodes = new Set();
  const seenCommunities = new Set();
  let total = 0;
  let woven = 0;
  let hops = 0;
  let streamDone = false;
  let busy = false;
  let dwell = 0;
  const target = new THREE.Vector3();

  function regionFor(c) {
    if (!regionOf.has(c) && known.has(c)) regionOf.set(c, cosmos.addProjectCommunity(known.get(c)));
    return regionOf.get(c);
  }

  function push(items) {
    for (const it of items) {
      if (it.t === 'community') {
        if (seenCommunities.has(it.id)) continue;
        seenCommunities.add(it.id);
        known.set(it.id, it);
        pending.push(it);
      } else if (it.t === 'node') {
        if (seenNodes.has(it.id)) continue;
        seenNodes.add(it.id);
        const last = groups[groups.length - 1];
        if (HEADS.has(it.kind)) {
          groups.push({ head: it, community: pending.splice(0), nodes: [], edges: [] });
          total++;
        } else if (last && it.parent !== undefined && !last.loose) last.nodes.push(it);
        else if (last && last.loose && last.head.c === it.c && last.nodes.length < LOOSE_MAX) last.nodes.push(it);
        else groups.push({ head: it, loose: true, community: pending.splice(0), nodes: [], edges: [] });
      } else if (it.t === 'edge') {
        if (groups.length) groups[groups.length - 1].edges.push(it);
        else late.push(it);
      }
    }
  }

  function materialize(g) {
    for (const n of g.nodes) cosmos.addProjectNode(n, regionFor(n.c));
    for (const e of g.edges) if (cosmos.addProjectEdge(e) < 0 && cosmos.nodeOf(e.a) < 0 !== cosmos.nodeOf(e.b) < 0) late.push(e);
  }

  function flushLate() {
    if (!late.length) return;
    const list = late.splice(0);
    for (const e of list) cosmos.addProjectEdge(e);
  }

  const files = (list) => list.reduce((k, g) => k + (g.loose ? 0 : 1), 0);

  function next() {
    const batch = Math.max(1, Math.min(Math.round(6 + 8 * speed), Math.ceil(Math.max(groups.length / 60, total / 160))));
    const first = groups.shift();
    const take = [first];
    while (take.length < batch && groups.length && groups[0].head.c === first.head.c && !groups[0].community.length) take.push(groups.shift());
    for (const c of first.community) if (!regionOf.has(c.id)) regionOf.set(c.id, cosmos.addProjectCommunity(c));
    const region = regionFor(first.head.c);
    const id = cosmos.addProjectNode(first.head, region);
    if (id < 0) {
      for (const g of take) materialize(g);
      woven += files(take);
      onProgress(woven, total, streamDone);
      return;
    }
    busy = true;
    hops++;
    target.set(first.head.pos[0], first.head.pos[1], first.head.pos[2]);
    const far = target.distanceTo(spider.pos) > 14;
    onHop(region, first.head, far);
    spider.jump(
      target,
      far
        ? { crouch: 0.3 / speed, speed: 20 * speed, min: 0.8 / speed, max: 1.8 / speed, burst: true, onLand: land }
        : { crouch: 0.05 / speed, speed: 32 * speed, min: 0.18 / speed, max: 0.5 / speed, arc: 0.35, burst: false, onLand: land }
    );
    function land() {
      if (!busy) return;
      materialize(first);
      cosmos.fire(id, 1.2);
      take.slice(1).forEach((g, k) => {
        const other = cosmos.addProjectNode(g.head, regionFor(g.head.c));
        materialize(g);
        if (other >= 0 && k < 3) cosmos.strike(id, other, 0.55);
      });
      flushLate();
      woven += files(take);
      onProgress(woven, total, streamDone);
      busy = false;
      dwell = groups.length > 30 ? 0.02 : 0.08 / speed;
    }
  }

  return {
    push,
    finish() {
      streamDone = true;
    },
    get speed() {
      return speed;
    },
    set speed(value) {
      speed = Math.max(0.1, Number(value) || 1);
    },
    get done() {
      return streamDone && !busy && groups.length === 0;
    },
    get stats() {
      return { hops, woven, total, backlog: groups.length };
    },
    update(dt) {
      if (busy) return;
      if (dwell > 0) {
        dwell -= dt;
        return;
      }
      if (!groups.length) flushLate();
      for (let k = 0; k < 200 && groups.length && !busy && !spider.airborne; k++) next();
    },
  };
}
