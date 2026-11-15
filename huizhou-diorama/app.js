(() => {
  "use strict";

  const MAP_SIZE = 4096;
  const INIT_CENTER_X4 = 2380.0;
  const INIT_CENTER_Y4 = 2230.0;
  const INIT_ZOOM = 1.45;

  const VEHICLE_PALETTES = [
    { body: "#d7d0c3", roof: "#ebe5d8", accent: "#394652", lenM: 4.1, widM: 1.75, v0: 8.0, kind: "car" },
    { body: "#455a68", roof: "#617b8c", accent: "#1e2a33", lenM: 4.3, widM: 1.80, v0: 8.2, kind: "car" },
    { body: "#8c4a3e", roof: "#aa6254", accent: "#2d1a18", lenM: 4.0, widM: 1.72, v0: 7.8, kind: "car" },
    { body: "#3f7a74", roof: "#589992", accent: "#1f3e3b", lenM: 6.4, widM: 2.10, v0: 6.2, kind: "bus" },
    { body: "#d6a44e", roof: "#ebc070", accent: "#382c16", lenM: 4.0, widM: 1.72, v0: 8.1, kind: "car" },
    { body: "#626870", roof: "#838a94", accent: "#232830", lenM: 4.2, widM: 1.78, v0: 7.9, kind: "car" }
  ];

  const PED_COLORS = [
    "#c95c48", "#3e6d8a", "#5f8a58", "#d49c4b",
    "#7c5d87", "#d9d2c5", "#4c5966", "#b87a52"
  ];

  const PIN_SCREEN_OFFSETS = {
    dong_qiaolou: { dx: -64, dy: -16 },
    xuguo_paifang: { dx: 12, dy: -14 },
    zhonghe_clock: { dx: 14, dy: -18 },
    nan_qiaolou: { dx: 0, dy: -14 },
    xi_chengmen: { dx: -24, dy: -8 }
  };

  const LANDMARK_MODELS = {
    xuguo_paifang: "./assets/models/xuguo_paifang.glb",
    dong_qiaolou: "./assets/models/dong_qiaolou.glb",
    nan_qiaolou: "./assets/models/nan_qiaolou.glb",
    huizhou_fuya: "./assets/models/fuya_zhengtang.glb"
  };

  function mulberry32(seed) {
    let a = seed >>> 0;
    return function () {
      a |= 0;
      a = (a + 0x6d2b79f5) | 0;
      let t = Math.imul(a ^ (a >>> 15), 1 | a);
      t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
  }

  function clamp(v, lo, hi) {
    return v < lo ? lo : v > hi ? hi : v;
  }

  function samplePolyline(pts, sTarget) {
    const n = pts.length;
    if (n === 0) return { x4: 0, y4: 0, tx: 1, ty: 0 };
    if (n === 1) return { x4: pts[0][0], y4: pts[0][1], tx: 1, ty: 0 };

    if (sTarget <= pts[0][2]) {
      const dx = pts[1][0] - pts[0][0];
      const dy = pts[1][1] - pts[0][1];
      const len = Math.hypot(dx, dy) || 1;
      return { x4: pts[0][0], y4: pts[0][1], tx: dx / len, ty: dy / len };
    }
    const last = pts[n - 1];
    if (sTarget >= last[2]) {
      const prev = pts[n - 2];
      const dx = last[0] - prev[0];
      const dy = last[1] - prev[1];
      const len = Math.hypot(dx, dy) || 1;
      return { x4: last[0], y4: last[1], tx: dx / len, ty: dy / len };
    }

    let lo = 0;
    let hi = n - 2;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      const sm = pts[mid][2];
      const sn = pts[mid + 1][2];
      if (sTarget < sm) {
        hi = mid - 1;
      } else if (sTarget > sn) {
        lo = mid + 1;
      } else {
        lo = mid;
        break;
      }
    }
    const i = clamp(lo, 0, n - 2);
    const p0 = pts[i];
    const p1 = pts[i + 1];
    const ds = p1[2] - p0[2];
    const t = ds > 1e-6 ? clamp((sTarget - p0[2]) / ds, 0, 1) : 0;
    const dx = p1[0] - p0[0];
    const dy = p1[1] - p0[1];
    const len = Math.hypot(dx, dy) || 1;
    return {
      x4: p0[0] + t * dx,
      y4: p0[1] + t * dy,
      tx: dx / len,
      ty: dy / len
    };
  }

  class WaterRenderer {
    constructor(canvas) {
      this.canvas = canvas;
      this.gl = canvas.getContext("webgl2", {
        alpha: true,
        antialias: false,
        premultipliedAlpha: true,
        powerPreference: "high-performance"
      });
      this.ready = false;
      this.program = null;
      this.vao = null;
      this.texBase = null;
      this.texMask = null;
      this.uLocs = null;
      this.cssW = 0;
      this.cssH = 0;
      this.dpr = 1;

      if (this.gl) {
        this._init();
      }
    }

    _compileShader(type, src) {
      const gl = this.gl;
      const s = gl.createShader(type);
      gl.shaderSource(s, src);
      gl.compileShader(s);
      if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) {
        const msg = gl.getShaderInfoLog(s);
        gl.deleteShader(s);
        throw new Error(`WebGL2 shader compile failed: ${msg}`);
      }
      return s;
    }

    _init() {
      const gl = this.gl;
      const vsSrc = `#version 300 es
        layout(location = 0) in vec2 a_pos;
        uniform vec2 u_viewportSize;
        out vec2 v_cssPos;
        void main() {
          gl_Position = vec4(a_pos, 0.0, 1.0);
          v_cssPos = vec2(
            (a_pos.x * 0.5 + 0.5) * u_viewportSize.x,
            (0.5 - a_pos.y * 0.5) * u_viewportSize.y
          );
        }
      `;
      const fsSrc = `#version 300 es
        precision highp float;
        in vec2 v_cssPos;
        uniform vec2 u_tl;
        uniform vec2 u_mapSize;
        uniform float u_time;
        uniform sampler2D u_base;
        uniform sampler2D u_mask;
        out vec4 fragColor;

        float hash21(vec2 p) {
          p = fract(p * vec2(123.34, 456.21));
          p += dot(p, p + 45.32);
          return fract(p.x * p.y);
        }

        float vnoise(vec2 p) {
          vec2 i = floor(p);
          vec2 f = fract(p);
          vec2 u = f * f * (3.0 - 2.0 * f);
          return mix(
            mix(hash21(i), hash21(i + vec2(1.0, 0.0)), u.x),
            mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0, 1.0)), u.x),
            u.y
          );
        }

        void main() {
          vec2 uv = (v_cssPos - u_tl) / max(u_mapSize, vec2(1.0));
          if (uv.x < 0.0 || uv.x > 1.0 || uv.y < 0.0 || uv.y > 1.0) {
            discard;
          }
          float mask = texture(u_mask, uv).r;
          if (mask < 0.025) {
            discard;
          }

          float edgeFade = smoothstep(0.08, 0.55, mask);
          float nLow = vnoise(uv * 42.0 + vec2(0.18 * u_time, -0.12 * u_time));
          vec2 wave = edgeFade * 0.00085 * vec2(
            sin(95.0 * uv.y + 4.2 * nLow + 1.35 * u_time),
            0.55 * cos(82.0 * uv.x + 3.8 * nLow - 1.1 * u_time)
          );
          vec2 dispUv = clamp(uv + wave, vec2(0.0), vec2(1.0));
          float maskDisp = texture(u_mask, dispUv).r;
          vec2 safeUv = mix(uv, dispUv, smoothstep(0.22, 0.65, maskDisp));
          vec3 col = texture(u_base, safeUv).rgb;

          vec2 rUv1 = vec2(uv.x * 86.0, uv.y * 290.0) + vec2(-0.55 * u_time, 0.32 * u_time);
          vec2 rUv2 = vec2(uv.x * 128.0, uv.y * 410.0) + vec2(0.42 * u_time, 0.24 * u_time);
          float warp1 = vnoise(rUv1 * 0.35);
          float warp2 = vnoise(rUv2 * 0.35 + vec2(17.3, 9.1));
          float rib1 = vnoise(rUv1 + 2.2 * vec2(warp1, warp2));
          float rib2 = vnoise(rUv2 - 1.8 * vec2(warp2, warp1));
          float swell = rib1 + rib2 - 1.0;

          float patchMask = smoothstep(0.54, 0.82, vnoise(uv * 26.0 + vec2(-0.08 * u_time, 0.06 * u_time)));
          float crest = smoothstep(0.66, 0.90, 0.5 + 0.5 * swell) * patchMask * edgeFade;

          col = clamp(
            col * (1.0 + 0.042 * swell * edgeFade) + vec3(0.09, 0.125, 0.12) * crest,
            0.0,
            1.0
          );
          fragColor = vec4(col * mask, mask);
        }
      `;

      const vs = this._compileShader(gl.VERTEX_SHADER, vsSrc);
      const fs = this._compileShader(gl.FRAGMENT_SHADER, fsSrc);
      const prog = gl.createProgram();
      gl.attachShader(prog, vs);
      gl.attachShader(prog, fs);
      gl.linkProgram(prog);
      if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) {
        throw new Error(`WebGL2 program link failed: ${gl.getProgramInfoLog(prog)}`);
      }
      this.program = prog;
      this.uLocs = {
        viewportSize: gl.getUniformLocation(prog, "u_viewportSize"),
        tl: gl.getUniformLocation(prog, "u_tl"),
        mapSize: gl.getUniformLocation(prog, "u_mapSize"),
        time: gl.getUniformLocation(prog, "u_time"),
        base: gl.getUniformLocation(prog, "u_base"),
        mask: gl.getUniformLocation(prog, "u_mask")
      };

      this.vao = gl.createVertexArray();
      gl.bindVertexArray(this.vao);
      const vbo = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, vbo);
      gl.bufferData(
        gl.ARRAY_BUFFER,
        new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]),
        gl.STATIC_DRAW
      );
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.bindVertexArray(null);

      this._loadTextures();
    }

    _createTexture(img) {
      const gl = this.gl;
      const tex = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      return tex;
    }

    _loadTextures() {
      const baseImg = new Image();
      const maskImg = new Image();
      let doneCount = 0;
      const checkReady = () => {
        doneCount += 1;
        if (doneCount === 2 && this.gl) {
          this.texBase = this._createTexture(baseImg);
          this.texMask = this._createTexture(maskImg);
          this.ready = true;
        }
      };
      baseImg.onload = checkReady;
      maskImg.onload = checkReady;
      baseImg.src = "./assets/water_base_2048.webp";
      maskImg.src = "./assets/water_mask_2048.png";
    }

    resize(cssW, cssH, dpr) {
      if (!this.gl) return;
      if (this.cssW === cssW && this.cssH === cssH && this.dpr === dpr) return;
      this.cssW = cssW;
      this.cssH = cssH;
      this.dpr = dpr;
      this.canvas.width = Math.max(1, Math.round(cssW * dpr));
      this.canvas.height = Math.max(1, Math.round(cssH * dpr));
      this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
    }

    render(tlX, tlY, mapW, mapH, timeSec, enabled) {
      if (!this.gl) return;
      const gl = this.gl;
      if (!enabled || !this.ready) {
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT);
        return;
      }
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(this.program);
      gl.bindVertexArray(this.vao);

      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, this.texBase);
      gl.uniform1i(this.uLocs.base, 0);

      gl.activeTexture(gl.TEXTURE1);
      gl.bindTexture(gl.TEXTURE_2D, this.texMask);
      gl.uniform1i(this.uLocs.mask, 1);

      gl.uniform2f(this.uLocs.viewportSize, this.cssW, this.cssH);
      gl.uniform2f(this.uLocs.tl, tlX, tlY);
      gl.uniform2f(this.uLocs.mapSize, mapW, mapH);
      gl.uniform1f(this.uLocs.time, timeSec);

      gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
      gl.bindVertexArray(null);
    }
  }

  class CitySimulator {
    constructor(simData) {
      this.rng = mulberry32(20261115);
      this.pxPerM = simData.meta.px_per_m || (4096 / 1360);
      this.lanes = simData.motor_lanes || [];
      this.laneById = new Map();
      for (const ln of this.lanes) {
        this.laneById.set(ln.id, ln);
        const pts = ln.points;
        const p0 = pts[0];
        const p1 = pts[1] || p0;
        const pn = pts[pts.length - 1];
        const pm = pts[pts.length - 2] || pn;
        const len0 = Math.hypot(p1[0] - p0[0], p1[1] - p0[1]) || 1;
        const len1 = Math.hypot(pn[0] - pm[0], pn[1] - pm[1]) || 1;
        ln.entryDir = [(p1[0] - p0[0]) / len0, (p1[1] - p0[1]) / len0];
        ln.exitDir = [(pn[0] - pm[0]) / len1, (pn[1] - pm[1]) / len1];
      }

      this.jboxes = new Map();
      for (const jb of simData.junction_boxes || []) {
        this.jboxes.set(jb.id, jb);
      }

      this.walkways = simData.ped_walkways || [];
      this.walkwayById = new Map();
      for (const wk of this.walkways) {
        this.walkwayById.set(wk.id, wk);
      }
      this.nodeToPedWays = simData.node_to_ped_ways || {};

      this.vehicles = [];
      this.pedestrians = [];
      this._spawnVehicles();
      this._spawnPedestrians();
    }

    _spawnVehicles() {
      const eligible = this.lanes.filter((ln) => ln.length_m >= 14.0);
      if (!eligible.length) return;
      const target = Math.min(54, Math.max(26, Math.floor(eligible.length / 4)));
      const laneOccupied = new Map();

      let guard = 0;
      while (this.vehicles.length < target && guard < 1200) {
        guard += 1;
        const ln = eligible[Math.floor(this.rng() * eligible.length)];
        const margin = 4.0;
        const s = margin + this.rng() * Math.max(1.0, ln.length_m - 2 * margin);
        const list = laneOccupied.get(ln.id) || [];
        if (list.some((otherS) => Math.abs(otherS - s) < 12.0)) continue;
        list.push(s);
        laneOccupied.set(ln.id, list);

        const pal = VEHICLE_PALETTES[Math.floor(this.rng() * VEHICLE_PALETTES.length)];
        const laneNext = this._chooseNextLane(ln);
        this.vehicles.push({
          id: this.vehicles.length,
          laneId: ln.id,
          nextLaneId: laneNext,
          s,
          v: pal.v0 * (0.55 + 0.35 * this.rng()),
          waitSec: 0,
          pal
        });
      }
    }

    _chooseNextLane(lane) {
      if (!lane.next_lanes || lane.next_lanes.length === 0) return -1;
      if (lane.next_lanes.length === 1) return lane.next_lanes[0];
      const [ex, ey] = lane.exitDir;
      const weights = [];
      let sum = 0;
      for (const nid of lane.next_lanes) {
        const nxt = this.laneById.get(nid);
        const dot = nxt ? ex * nxt.entryDir[0] + ey * nxt.entryDir[1] : 0;
        const w = Math.max(0.2, 1.4 + dot);
        weights.push(w);
        sum += w;
      }
      let r = this.rng() * sum;
      for (let i = 0; i < lane.next_lanes.length; i++) {
        r -= weights[i];
        if (r <= 0) return lane.next_lanes[i];
      }
      return lane.next_lanes[0];
    }

    _spawnPedestrians() {
      if (!this.walkways.length) return;
      const totalWeight = this.walkways.reduce((acc, w) => acc + (w.weight || 1), 0);
      const count = 108;
      for (let i = 0; i < count; i++) {
        let r = this.rng() * totalWeight;
        let picked = this.walkways[0];
        for (const wk of this.walkways) {
          r -= wk.weight || 1;
          if (r <= 0) {
            picked = wk;
            break;
          }
        }
        const s = this.rng() * picked.length_m;
        const dir = this.rng() < 0.5 ? 1 : -1;
        this.pedestrians.push({
          wayId: picked.id,
          s,
          dir,
          speed: 1.05 + this.rng() * 0.55,
          phase: this.rng() * Math.PI * 2,
          color: PED_COLORS[Math.floor(this.rng() * PED_COLORS.length)],
          hasUmbrella: this.rng() < 0.09
        });
      }
    }

    _isJunctionGreen(jbId, approachGroup, simTimeSec) {
      const jb = this.jboxes.get(jbId);
      if (!jb) return true;
      const cyc = jb.cycle_sec || 70.0;
      const t = (simTimeSec + (jb.phase_offset_sec || 0)) % cyc;
      if (approachGroup === 0) {
        return t < 31.0;
      }
      return t >= 35.0 && t < 66.0;
    }

    step(dtSec, simTimeSec) {
      const dt = Math.min(dtSec, 0.05);
      if (dt <= 0) return;

      // 按车道聚合并按 s 降序排列（最前方车辆在前）
      const byLane = new Map();
      for (const car of this.vehicles) {
        let arr = byLane.get(car.laneId);
        if (!arr) {
          arr = [];
          byLane.set(car.laneId, arr);
        }
        arr.push(car);
      }
      for (const arr of byLane.values()) {
        arr.sort((a, b) => b.s - a.s);
      }

      // IDM 更新
      const aMax = 1.4;
      const bComf = 2.2;
      const s0 = 2.2;
      const T = 1.3;

      for (const arr of byLane.values()) {
        for (let i = 0; i < arr.length; i++) {
          const car = arr[i];
          const lane = this.laneById.get(car.laneId);
          if (!lane) continue;

          let sGap = 120.0;
          let dv = 0.0;

          if (i > 0) {
            const lead = arr[i - 1];
            sGap = lead.s - car.s - 0.5 * (lead.pal.lenM + car.pal.lenM);
            dv = car.v - lead.v;
          } else if (car.nextLaneId >= 0) {
            const nextArr = byLane.get(car.nextLaneId);
            if (nextArr && nextArr.length > 0) {
              const tailLead = nextArr[nextArr.length - 1];
              const gapNext = (lane.length_m - car.s) + tailLead.s - 0.5 * (tailLead.pal.lenM + car.pal.lenM);
              if (gapNext < sGap) {
                sGap = gapNext;
                dv = car.v - tailLead.v;
              }
            }
          }

          // 20 米逻辑路口信号灯与 12 秒防死锁控制
          if (lane.to_junction_id && car.waitSec <= 12.0) {
            const distEnd = lane.length_m - car.s;
            if (distEnd > 0.5 && distEnd < 16.0) {
              const green = this._isJunctionGreen(lane.to_junction_id, lane.approach_group, simTimeSec);
              if (!green) {
                const stopDist = Math.max(0.25, distEnd - 2.6);
                if (stopDist < sGap) {
                  sGap = stopDist;
                  dv = car.v;
                }
              }
            }
          }

          const v0 = car.pal.v0;
          const sStar = s0 + Math.max(0.0, car.v * T + (car.v * dv) / (2.0 * Math.sqrt(aMax * bComf)));
          const effGap = Math.max(0.35, sGap);
          let acc = aMax * (1.0 - Math.pow(car.v / v0, 4) - Math.pow(sStar / effGap, 2));
          acc = clamp(acc, -6.5, 2.0);
          car.v = clamp(car.v + acc * dt, 0.0, v0 * 1.15);
          car.s += car.v * dt;

          if (car.v < 0.25) {
            car.waitSec += dt;
          } else {
            car.waitSec = 0;
          }
        }
      }

      // 车道切换与边界循环
      for (const car of this.vehicles) {
        const lane = this.laneById.get(car.laneId);
        if (!lane) continue;
        if (car.s >= lane.length_m) {
          const overflow = car.s - lane.length_m;
          if (car.nextLaneId >= 0) {
            const nxt = this.laneById.get(car.nextLaneId);
            if (nxt) {
              car.laneId = nxt.id;
              car.s = Math.min(overflow, Math.max(0.1, nxt.length_m * 0.5));
              car.nextLaneId = this._chooseNextLane(nxt);
              car.waitSec = 0;
              continue;
            }
          }
          // 若驶出边界死端，则切换至有足够间距的新起点
          let moved = false;
          for (let attempt = 0; attempt < 25; attempt++) {
            const cand = this.lanes[Math.floor(this.rng() * this.lanes.length)];
            if (cand.length_m < 14.0) continue;
            const list = byLane.get(cand.id);
            if (list && list.some((other) => other.s < 14.0)) continue;
            car.laneId = cand.id;
            car.s = 1.5;
            car.v = car.pal.v0 * 0.65;
            car.nextLaneId = this._chooseNextLane(cand);
            car.waitSec = 0;
            moved = true;
            break;
          }
          if (!moved) {
            car.s = 0.5;
            car.waitSec = 0;
          }
        }
      }

      // 古巷行人步态与节点转向
      for (const ped of this.pedestrians) {
        const wk = this.walkwayById.get(ped.wayId);
        if (!wk) continue;
        ped.s += ped.dir * ped.speed * dt;
        ped.phase += ped.speed * dt * 4.8;

        if (ped.s >= wk.length_m || ped.s <= 0) {
          const hitNode = ped.s >= wk.length_m ? wk.to_node : wk.from_node;
          const adj = this.nodeToPedWays[hitNode] || [];
          const others = adj.filter((wid) => wid !== ped.wayId);
          const pool = others.length > 0 ? others : adj;
          if (pool.length > 0) {
            const nxtId = pool[Math.floor(this.rng() * pool.length)];
            const nxtWk = this.walkwayById.get(nxtId);
            if (nxtWk) {
              ped.wayId = nxtWk.id;
              if (nxtWk.from_node === hitNode) {
                ped.dir = 1;
                ped.s = 0.05;
              } else {
                ped.dir = -1;
                ped.s = Math.max(0.05, nxtWk.length_m - 0.05);
              }
              continue;
            }
          }
          ped.dir *= -1;
          ped.s = clamp(ped.s, 0.05, Math.max(0.1, wk.length_m - 0.05));
        }
      }
    }

    collectVisibleSprites(minX4, minY4, maxX4, maxY4, showCars, showPeds) {
      const list = [];
      if (showCars) {
        for (const car of this.vehicles) {
          const ln = this.laneById.get(car.laneId);
          if (!ln) continue;
          const sample = samplePolyline(ln.points, car.s);
          if (sample.x4 < minX4 || sample.x4 > maxX4 || sample.y4 < minY4 || sample.y4 > maxY4) {
            continue;
          }
          list.push({
            kind: "car",
            x4: sample.x4,
            y4: sample.y4,
            tx: sample.tx,
            ty: sample.ty,
            pal: car.pal
          });
        }
      }
      if (showPeds) {
        for (const ped of this.pedestrians) {
          const wk = this.walkwayById.get(ped.wayId);
          if (!wk) continue;
          const sample = samplePolyline(wk.points, ped.s);
          if (sample.x4 < minX4 || sample.x4 > maxX4 || sample.y4 < minY4 || sample.y4 > maxY4) {
            continue;
          }
          list.push({
            kind: "ped",
            x4: sample.x4,
            y4: sample.y4,
            bob: Math.abs(Math.sin(ped.phase)),
            color: ped.color,
            hasUmbrella: ped.hasUmbrella
          });
        }
      }
      list.sort((a, b) => a.y4 - b.y4);
      return list;
    }
  }

  function drawCarSprite(ctx, sx, sy, tx, ty, pal, pxPerM, scale) {
    const drawScale = Math.max(scale, 0.25);
    const L = pal.lenM * pxPerM * drawScale;
    const W = pal.widM * pxPerM * drawScale;
    const angle = Math.atan2(ty, tx);

    ctx.save();
    ctx.translate(sx, sy);

    // 地面投影
    ctx.save();
    ctx.translate(1.2 * drawScale, 1.4 * drawScale);
    ctx.rotate(angle);
    ctx.fillStyle = "rgba(12, 16, 20, 0.42)";
    ctx.fillRect(-L * 0.52, -W * 0.55, L * 1.04, W * 1.1);
    ctx.restore();

    // 车身下层
    ctx.save();
    ctx.rotate(angle);
    ctx.fillStyle = pal.body;
    ctx.fillRect(-L * 0.5, -W * 0.5, L, W);

    // 前窗/尾灯微细节
    ctx.fillStyle = pal.accent;
    ctx.fillRect(L * 0.14, -W * 0.40, L * 0.16, W * 0.80);
    if (drawScale >= 0.55) {
      ctx.fillStyle = "rgba(255, 240, 175, 0.85)";
      ctx.fillRect(L * 0.45, -W * 0.40, Math.max(1, L * 0.06), W * 0.24);
      ctx.fillRect(L * 0.45, W * 0.16, Math.max(1, L * 0.06), W * 0.24);
      ctx.fillStyle = "rgba(220, 65, 50, 0.85)";
      ctx.fillRect(-L * 0.51, -W * 0.36, Math.max(1, L * 0.05), W * 0.22);
      ctx.fillRect(-L * 0.51, W * 0.14, Math.max(1, L * 0.05), W * 0.22);
    }
    ctx.restore();

    // 等轴测上移车顶层，体现三维高度厚度
    ctx.save();
    ctx.translate(0, -1.65 * drawScale);
    ctx.rotate(angle);
    ctx.fillStyle = pal.roof;
    const roofLen = pal.kind === "bus" ? L * 0.78 : L * 0.50;
    const roofOff = pal.kind === "bus" ? -roofLen * 0.5 : -roofLen * 0.58;
    ctx.fillRect(roofOff, -W * 0.38, roofLen, W * 0.76);
    ctx.restore();

    ctx.restore();
  }

  function drawPedSprite(ctx, sx, sy, bob, color, hasUmbrella, scale) {
    const s = Math.max(scale, 0.32);
    const bounce = bob * 0.7 * s;

    // 地面微型影子
    ctx.fillStyle = "rgba(15, 20, 24, 0.36)";
    ctx.fillRect(sx - 1.3 * s, sy - 0.6 * s, 2.8 * s, 1.5 * s);

    // 深色下装
    ctx.fillStyle = "#222930";
    ctx.fillRect(sx - 0.9 * s, sy - 2.3 * s - bounce, 1.8 * s, 2.2 * s);

    // 上衣
    ctx.fillStyle = color;
    ctx.fillRect(sx - 1.05 * s, sy - 4.4 * s - bounce, 2.1 * s, 2.3 * s);

    // 头部 / 油纸伞
    if (hasUmbrella && s >= 0.45) {
      ctx.fillStyle = "#d9c39e";
      ctx.fillRect(sx - 2.1 * s, sy - 6.3 * s - bounce, 4.2 * s, 1.8 * s);
      ctx.fillStyle = "#a34f3d";
      ctx.fillRect(sx - 1.4 * s, sy - 6.8 * s - bounce, 2.8 * s, 0.9 * s);
    } else {
      ctx.fillStyle = "#ebd4be";
      ctx.fillRect(sx - 0.8 * s, sy - 5.6 * s - bounce, 1.6 * s, 1.35 * s);
    }
  }

  async function bootstrap() {
    if (typeof OpenSeadragon === "undefined") {
      throw new Error("OpenSeadragon 脚本未加载");
    }

    const stage = document.getElementById("stage");
    const waterCanvas = document.getElementById("water-gl-canvas");
    const simCanvas = document.getElementById("sim-canvas");
    const simCtx = simCanvas.getContext("2d");
    const pinsContainer = document.getElementById("landmark-pins");
    const dockContainer = document.getElementById("landmark-dock");

    const toggleTraffic = document.getElementById("toggle-traffic");
    const togglePeds = document.getElementById("toggle-peds");
    const toggleWater = document.getElementById("toggle-water");
    const toggleOcclusion = document.getElementById("toggle-occlusion");
    const toggleTiltshift = document.getElementById("toggle-tiltshift");
    const togglePins = document.getElementById("toggle-pins");
    const tsTop = document.getElementById("tilt-shift-top");
    const tsBot = document.getElementById("tilt-shift-bottom");

    const teleFps = document.getElementById("tele-fps");
    const teleCars = document.getElementById("tele-cars");
    const telePeds = document.getElementById("tele-peds");
    const teleZoom = document.getElementById("tele-zoom");

    const cardEl = document.getElementById("landmark-card");
    const cardBadge = document.getElementById("card-badge");
    const cardTitle = document.getElementById("card-title");
    const cardDesc = document.getElementById("card-desc");
    const cardCoords = document.getElementById("card-coords");

    const hudEl = document.getElementById("hud-controls");
    const btnCollapse = document.getElementById("btn-collapse-hud");
    btnCollapse.addEventListener("click", () => {
      const collapsed = hudEl.classList.toggle("is-collapsed");
      btnCollapse.textContent = collapsed ? "展开" : "收起";
    });

    let simSpeed = 1.0;
    for (const btn of document.querySelectorAll(".speed-btn")) {
      btn.addEventListener("click", () => {
        simSpeed = parseFloat(btn.dataset.speed || "1");
        document.querySelectorAll(".speed-btn").forEach((b) => b.classList.toggle("is-active", b === btn));
      });
    }

    toggleTiltshift.addEventListener("change", () => {
      const hidden = !toggleTiltshift.checked;
      tsTop.classList.toggle("is-hidden", hidden);
      tsBot.classList.toggle("is-hidden", hidden);
    });

    toggleWater.addEventListener("change", () => {
      waterCanvas.style.display = toggleWater.checked ? "block" : "none";
    });

    togglePins.addEventListener("change", () => {
      pinsContainer.style.display = togglePins.checked ? "block" : "none";
    });

    const resp = await fetch("./assets/sim_network.json");
    if (!resp.ok) {
      throw new Error(`无法加载 sim_network.json: HTTP ${resp.status}`);
    }
    const simData = await resp.json();
    const simulator = new CitySimulator(simData);
    const landmarks = simData.landmarks || [];

    const fgImage = new Image();
    let fgReady = false;
    fgImage.onload = () => {
      fgReady = true;
    };
    fgImage.src = "./assets/foreground_occlusion_4k.png";

    const waterRenderer = new WaterRenderer(waterCanvas);

    if (typeof OpenSeadragon.setImageFormatsSupported === "function") {
      OpenSeadragon.setImageFormatsSupported({ webp: true });
    }

    const viewer = OpenSeadragon({
      id: "osd-viewer",
      tileSources: "./huizhou_dzi.dzi",
      showNavigationControl: false,
      showHomeControl: false,
      showZoomControl: false,
      showFullPageControl: false,
      minZoomImageRatio: 0.85,
      maxZoomPixelRatio: 2.8,
      visibilityRatio: 0.9,
      animationTime: 0.85,
      constrainDuringPan: true,
      gestureSettingsMouse: {
        clickToZoom: false,
        dblClickToZoom: true
      }
    });

    let osdOpen = false;
    let activeLandmark = null;
    const pinEls = new Map();
    const dockEls = new Map();

    function selectLandmark(lm, shouldFly = true) {
      activeLandmark = lm;
      for (const [id, el] of pinEls.entries()) {
        el.classList.toggle("is-active", lm && id === lm.id);
      }
      for (const [id, el] of dockEls.entries()) {
        el.classList.toggle("is-active", lm && id === lm.id);
      }
      if (!lm) {
        cardEl.classList.add("is-hidden");
        hide3DViewer();
        return;
      }
      cardBadge.textContent = lm.badge || "历史地标";
      cardTitle.textContent = lm.title;
      cardDesc.textContent = lm.desc;
      cardCoords.textContent = `4K (${Math.round(lm.x4)}, ${Math.round(lm.y4)})`;
      cardEl.classList.remove("is-hidden");
      sync3DButtonForLandmark(lm);

      if (shouldFly && osdOpen) {
        viewer.viewport.panTo(new OpenSeadragon.Point(lm.x4 / MAP_SIZE, lm.y4 / MAP_SIZE));
        viewer.viewport.zoomTo(lm.zoom || 4.0);
      }
    }

    const card3dWrap = document.getElementById("card-3d-wrap");
    const card3dCanvas = document.getElementById("card-3d-canvas");
    const card3dStatus = document.getElementById("card-3d-status");
    const btnToggle3d = document.getElementById("btn-toggle-3d");
    let threeCtx = null;
    let threeOpen = false;
    let loadedModelUrl = null;

    function hide3DViewer() {
      threeOpen = false;
      card3dWrap.classList.add("is-hidden");
      btnToggle3d.classList.remove("is-active");
      btnToggle3d.textContent = "查看 3D 模型";
    }

    function sync3DButtonForLandmark(lm) {
      hide3DViewer();
      if (lm && LANDMARK_MODELS[lm.id] && window.THREE && THREE.GLTFLoader) {
        btnToggle3d.classList.remove("is-hidden");
      } else {
        btnToggle3d.classList.add("is-hidden");
      }
    }

    function ensureThreeCtx() {
      if (threeCtx) return threeCtx;
      const w = card3dWrap.clientWidth || 300;
      const h = card3dWrap.clientHeight || 196;
      const renderer = new THREE.WebGLRenderer({ canvas: card3dCanvas, antialias: true, alpha: true });
      renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
      renderer.setSize(w, h, false);
      renderer.outputEncoding = THREE.sRGBEncoding;

      const scene = new THREE.Scene();
      const camera = new THREE.PerspectiveCamera(38, w / h, 0.05, 100);
      camera.position.set(2.2, 1.5, 2.2);

      scene.add(new THREE.AmbientLight(0xfff5e4, 0.95));
      const dir1 = new THREE.DirectionalLight(0xfff0d4, 1.15);
      dir1.position.set(3, 5, 4);
      scene.add(dir1);
      const dir2 = new THREE.DirectionalLight(0x9ec5e8, 0.45);
      dir2.position.set(-3, 2, -3);
      scene.add(dir2);

      const controls = new THREE.OrbitControls(camera, card3dCanvas);
      controls.enableDamping = true;
      controls.dampingFactor = 0.08;
      controls.autoRotate = true;
      controls.autoRotateSpeed = 1.4;

      const loader = new THREE.GLTFLoader();
      const modelGroup = new THREE.Group();
      scene.add(modelGroup);

      function renderLoop() {
        requestAnimationFrame(renderLoop);
        if (!threeOpen) return;
        controls.update();
        renderer.render(scene, camera);
      }
      renderLoop();

      threeCtx = { renderer, scene, camera, controls, loader, modelGroup };
      return threeCtx;
    }

    function open3DForLandmark(lm) {
      const url = lm && LANDMARK_MODELS[lm.id];
      if (!url) return;
      threeOpen = true;
      card3dWrap.classList.remove("is-hidden");
      btnToggle3d.classList.add("is-active");
      btnToggle3d.textContent = "收起 3D 模型";

      const ctx = ensureThreeCtx();
      const w = card3dWrap.clientWidth || 300;
      const h = card3dWrap.clientHeight || 196;
      ctx.renderer.setSize(w, h, false);
      ctx.camera.aspect = w / h;
      ctx.camera.updateProjectionMatrix();

      if (loadedModelUrl === url) {
        card3dStatus.textContent = "拖拽旋转 · 滚轮缩放";
        return;
      }
      loadedModelUrl = url;
      while (ctx.modelGroup.children.length > 0) {
        ctx.modelGroup.remove(ctx.modelGroup.children[0]);
      }
      card3dStatus.textContent = "加载 3D 模型中…";
      ctx.loader.load(
        url,
        (gltf) => {
          if (loadedModelUrl !== url) return;
          const root = gltf.scene;
          const box = new THREE.Box3().setFromObject(root);
          const size = box.getSize(new THREE.Vector3());
          const center = box.getCenter(new THREE.Vector3());
          const maxDim = Math.max(size.x, size.y, size.z, 0.001);
          const scale = 1.85 / maxDim;
          root.scale.setScalar(scale);
          root.position.set(-center.x * scale, -center.y * scale, -center.z * scale);
          ctx.modelGroup.add(root);
          ctx.camera.position.set(2.1, 1.35, 2.1);
          ctx.controls.target.set(0, 0, 0);
          ctx.controls.update();
          card3dStatus.textContent = "拖拽旋转 · 滚轮缩放";
        },
        undefined,
        () => {
          card3dStatus.textContent = "3D 模型加载失败";
        }
      );
    }

    btnToggle3d.addEventListener("click", () => {
      if (threeOpen) {
        hide3DViewer();
      } else if (activeLandmark) {
        open3DForLandmark(activeLandmark);
      }
    });

    for (const lm of landmarks) {
      const pin = document.createElement("button");
      pin.type = "button";
      pin.className = "lm-pin";
      pin.textContent = lm.short_title || lm.title;
      pin.addEventListener("click", (ev) => {
        ev.stopPropagation();
        selectLandmark(lm, true);
      });
      pinsContainer.appendChild(pin);
      pinEls.set(lm.id, pin);

      const dockBtn = document.createElement("button");
      dockBtn.type = "button";
      dockBtn.className = "dock-btn";
      dockBtn.textContent = lm.short_title || lm.title;
      dockBtn.addEventListener("click", () => selectLandmark(lm, true));
      dockContainer.appendChild(dockBtn);
      dockEls.set(lm.id, dockBtn);
    }

    document.getElementById("btn-close-card").addEventListener("click", () => selectLandmark(null, false));
    document.getElementById("btn-refocus-card").addEventListener("click", () => {
      if (activeLandmark) selectLandmark(activeLandmark, true);
    });

    document.getElementById("btn-zoom-in").addEventListener("click", () => {
      if (osdOpen) viewer.viewport.zoomBy(1.35);
    });
    document.getElementById("btn-zoom-out").addEventListener("click", () => {
      if (osdOpen) viewer.viewport.zoomBy(1 / 1.35);
    });
    document.getElementById("btn-reset-view").addEventListener("click", () => {
      if (!osdOpen) return;
      selectLandmark(null, false);
      viewer.viewport.panTo(new OpenSeadragon.Point(INIT_CENTER_X4 / MAP_SIZE, INIT_CENTER_Y4 / MAP_SIZE));
      viewer.viewport.zoomTo(INIT_ZOOM);
    });

    // WebKit 移动端/桌面移轴景深防鬼影微抖动（指南第 7 节）
    let blurToggle = false;
    viewer.addHandler("update-viewport", () => {
      if (!toggleTiltshift.checked) return;
      blurToggle = !blurToggle;
      stage.style.setProperty("--ts-blur", blurToggle ? "5.0005px" : "5.0000px");
    });

    viewer.addHandler("open", () => {
      osdOpen = true;
      viewer.viewport.panTo(new OpenSeadragon.Point(INIT_CENTER_X4 / MAP_SIZE, INIT_CENTER_Y4 / MAP_SIZE), true);
      viewer.viewport.zoomTo(INIT_ZOOM, null, true);
    });

    let lastNow = performance.now();
    let simTimeSec = 0;
    let fpsFrames = 0;
    let fpsLastUpdate = lastNow;
    let curFps = 60;
    let lastCssW = 0;
    let lastCssH = 0;
    let lastDpr = 1;

    function tick(now) {
      requestAnimationFrame(tick);
      const rawDt = Math.min(0.05, Math.max(0.0, (now - lastNow) / 1000.0));
      lastNow = now;

      const dt = rawDt * simSpeed;
      simTimeSec += dt;
      simulator.step(dt, simTimeSec);

      fpsFrames += 1;
      if (now - fpsLastUpdate >= 450) {
        curFps = Math.round((fpsFrames * 1000.0) / (now - fpsLastUpdate));
        fpsFrames = 0;
        fpsLastUpdate = now;
      }

      if (!osdOpen) return;

      const rect = stage.getBoundingClientRect();
      const cssW = rect.width;
      const cssH = rect.height;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      if (cssW <= 0 || cssH <= 0) return;

      if (cssW !== lastCssW || cssH !== lastCssH || dpr !== lastDpr) {
        lastCssW = cssW;
        lastCssH = cssH;
        lastDpr = dpr;
        simCanvas.width = Math.max(1, Math.round(cssW * dpr));
        simCanvas.height = Math.max(1, Math.round(cssH * dpr));
        waterRenderer.resize(cssW, cssH, dpr);
      }

      // current=true 锁定当前动画插值帧，确保所有覆盖层零滞后对齐
      const tl = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(0, 0), true);
      const br = viewer.viewport.pixelFromPoint(new OpenSeadragon.Point(1, 1), true);
      const mapW = br.x - tl.x;
      const mapH = br.y - tl.y;
      const scale = mapW / MAP_SIZE;

      waterRenderer.render(tl.x, tl.y, mapW, mapH, now * 0.001, toggleWater.checked);

      simCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
      simCtx.clearRect(0, 0, cssW, cssH);

      const minX4 = Math.max(-32, -tl.x / scale - 28);
      const minY4 = Math.max(-32, -tl.y / scale - 28);
      const maxX4 = Math.min(MAP_SIZE + 32, (cssW - tl.x) / scale + 28);
      const maxY4 = Math.min(MAP_SIZE + 32, (cssH - tl.y) / scale + 28);

      const sprites = simulator.collectVisibleSprites(
        minX4,
        minY4,
        maxX4,
        maxY4,
        toggleTraffic.checked,
        togglePeds.checked
      );

      for (const sp of sprites) {
        const sx = tl.x + sp.x4 * scale;
        const sy = tl.y + sp.y4 * scale;
        if (sp.kind === "car") {
          drawCarSprite(simCtx, sx, sy, sp.tx, sp.ty, sp.pal, simulator.pxPerM, scale);
        } else {
          drawPedSprite(simCtx, sx, sy, sp.bob, sp.color, sp.hasUmbrella, scale);
        }
      }

      if (toggleOcclusion.checked && fgReady) {
        const sx0 = Math.max(0, Math.floor(-tl.x / scale) - 2);
        const sy0 = Math.max(0, Math.floor(-tl.y / scale) - 2);
        const sx1 = Math.min(MAP_SIZE, Math.ceil((cssW - tl.x) / scale) + 2);
        const sy1 = Math.min(MAP_SIZE, Math.ceil((cssH - tl.y) / scale) + 2);
        if (sx1 > sx0 && sy1 > sy0) {
          const sw = sx1 - sx0;
          const sh = sy1 - sy0;
          simCtx.imageSmoothingEnabled = scale < 1.35;
          simCtx.drawImage(
            fgImage,
            sx0,
            sy0,
            sw,
            sh,
            tl.x + sx0 * scale,
            tl.y + sy0 * scale,
            sw * scale,
            sh * scale
          );
        }
      }

      if (togglePins.checked) {
        for (const lm of landmarks) {
          const pin = pinEls.get(lm.id);
          if (!pin) continue;
          const off = PIN_SCREEN_OFFSETS[lm.id] || { dx: 0, dy: 0 };
          const px = tl.x + lm.x4 * scale + off.dx;
          const py = tl.y + lm.y4 * scale + off.dy;
          if (px < -40 || py < -20 || px > cssW + 40 || py > cssH + 40) {
            pin.style.transform = "translate3d(-9999px, -9999px, 0)";
          } else {
            pin.style.transform = `translate3d(${px.toFixed(1)}px, ${py.toFixed(1)}px, 0)`;
          }
        }
      }

      const curZoom = viewer.viewport.getZoom(true);
      teleFps.textContent = `${curFps} FPS`;
      teleCars.textContent = `车 ${toggleTraffic.checked ? simulator.vehicles.length : 0}`;
      telePeds.textContent = `人 ${togglePeds.checked ? simulator.pedestrians.length : 0}`;
      teleZoom.textContent = `${curZoom.toFixed(2)}×`;
    }

    requestAnimationFrame(tick);
  }

  window.addEventListener("DOMContentLoaded", () => {
    bootstrap().catch((err) => {
      console.error("[HuizhouDiorama] 初始化失败:", err);
      const badge = document.getElementById("tele-fps");
      if (badge) badge.textContent = "加载失败";
    });
  });
})();
