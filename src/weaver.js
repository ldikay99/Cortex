import * as THREE from 'three';

export function createWeaver({ cosmos, spider, speed = 1, onHop, onProgress }) {
  const groups = [];
  const regionOf = new Map();
  const pending = [];
  const seenNodes = new Set();
  const seenCommunities = new Set();
  let total = 0;
  let woven = 0;
  let streamDone = false;
  let busy = false;
  let dwell = 0;
  const target = new THREE.Vector3();

  function push(items) {
    for (const it of items) {
      if (it.t === 'community') {
        if (seenCommunities.has(it.id)) continue;
        seenCommunities.add(it.id);
        pending.push(it);
      } else if (it.t === 'node') {
        if (seenNodes.has(it.id)) continue;
        seenNodes.add(it.id);
        if (it.kind === 'module' || it.kind === 'doc') {
          groups.push({ head: it, community: pending.length ? pending.splice(0) : [], nodes: [], edges: [] });
          total++;
        } else if (groups.length) groups[groups.length - 1].nodes.push(it);
      } else if (groups.length) groups[groups.length - 1].edges.push(it);
    }
  }

  function materialize(g) {
    for (const n of g.nodes) cosmos.addProjectNode(n, regionOf.get(n.c));
    for (const e of g.edges) cosmos.addProjectEdge(e);
  }

  function next() {
    const batch = Math.max(1, Math.min(8, Math.ceil(groups.length / 90)));
    const first = groups.shift();
    const take = [first];
    while (take.length < batch && groups.length && groups[0].head.c === first.head.c && !groups[0].community.length) take.push(groups.shift());
    for (const c of first.community) regionOf.set(c.id, cosmos.addProjectCommunity(c));
    const region = regionOf.get(first.head.c);
    const id = cosmos.addProjectNode(first.head, region);
    if (id < 0) {
      woven += take.length;
      onProgress(woven, total, streamDone);
      return;
    }
    busy = true;
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
        const other = cosmos.addProjectNode(g.head, regionOf.get(g.head.c));
        materialize(g);
        if (other >= 0 && k < 3) cosmos.strike(id, other, 0.55);
      });
      woven += take.length;
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
    update(dt) {
      if (busy) return;
      if (dwell > 0) {
        dwell -= dt;
        return;
      }
      for (let k = 0; k < 200 && groups.length && !busy && !spider.airborne; k++) next();
    },
  };
}
