// The 3D progress scenes.
//
// Each scene is a small plug-in in its own file. It exports:
//   { id, calm, create(ctx) }   where create() builds its objects and returns { update(state, dt, time) }.
// ctx gives it THREE, the scene to add things to, the theme's colors, and ctx.view.halfW / halfH
// (half the visible width and height, which change with the screen).
// state is { progress: 0..1 (smoothed), status: "running" | "done" | "failed", ended: seconds since it ended }.
//
// To add a scene: write the file, import it below and add it to SCENES (or CALM).
// The rest of the app only talks to window.joyshareScenes.
import * as THREE from "/vendor/three.module.min.js";

import blackhole from "./blackhole.js";
import bloom from "./bloom.js";
import compressor from "./compressor.js";
import demolition from "./demolition.js";
import dominoes from "./dominoes.js";
import mascots from "./mascot.js";
import ring from "./ring.js";
import rocket from "./rocket.js";
import ufo from "./ufo.js";
import voyage from "./voyage.js";

const SCENES = [demolition, compressor, voyage, rocket, blackhole, dominoes, ufo];   // the full ones
const CALM = [ring, bloom];                        // slow and steady, for people with "Reduce motion" on
const HALF_HEIGHT = 3;                             // every scene is 6 units tall; width follows the screen

function themeColors() {
  const css = getComputedStyle(document.documentElement);
  const read = (name, fallback) => {
    const value = css.getPropertyValue(name).trim();
    try { return new THREE.Color(value && !value.includes("gradient") ? value : fallback); } catch { return new THREE.Color(fallback); }
  };
  return { hot: read("--hot", "#ff2f92"), zap: read("--zap", "#c8ff2e"), third: read("--third", "#ff8a1f"),
    ink: read("--ink", "#ffffff"), muted: read("--muted", "#888888") };
}

class Stage {
  constructor(container, definition) {
    this.container = container;
    this.definition = definition;
    this.canvas = document.createElement("canvas");
    this.canvas.setAttribute("aria-hidden", "true"); // the percentage next to it is the readable version
    container.replaceChildren(this.canvas);
    this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, alpha: true, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.OrthographicCamera(-1, 1, HALF_HEIGHT, -HALF_HEIGHT, 0.1, 100);
    this.camera.position.set(0, 1.4, 12);
    this.camera.lookAt(0, 0, 0);
    this.scene.add(new THREE.AmbientLight(0xffffff, 1.5));
    const sun = new THREE.DirectionalLight(0xffffff, 2.2);
    sun.position.set(3, 6, 8);
    this.scene.add(sun);

    this.view = { halfW: HALF_HEIGHT, halfH: HALF_HEIGHT };
    this.state = { progress: 0, status: "running", ended: 0 };
    this.target = 0;
    this.resize();
    this.observer = new ResizeObserver(() => this.resize());
    this.observer.observe(container);
    this.actor = definition.create({ THREE, scene: this.scene, colors: themeColors(), view: this.view });
    this.last = performance.now();
    this.frame = requestAnimationFrame((now) => this.loop(now));
  }

  resize() {
    const width = Math.max(this.container.clientWidth, 50), height = Math.max(this.container.clientHeight, 50);
    this.renderer.setSize(width, height, false);
    this.view.halfW = HALF_HEIGHT * (width / height);
    this.camera.left = -this.view.halfW;
    this.camera.right = this.view.halfW;
    this.camera.updateProjectionMatrix();
  }

  // Progress never goes backwards, even when the job moves from downloading to converting.
  set(progress, status) {
    this.target = Math.max(this.target, Math.min(Math.max(progress, 0), 1));
    if (status === "done") this.target = 1;
    this.state.status = status;
  }

  loop(now) {
    this.frame = requestAnimationFrame((next) => this.loop(next));
    const dt = Math.min((now - this.last) / 1000, 0.05);
    this.last = now;
    if (document.hidden) return; // don't spend battery on a tab nobody is looking at
    const state = this.state;
    state.progress += (this.target - state.progress) * Math.min(1, dt * 4);
    if (state.status !== "running") state.ended += dt;
    this.actor.update(state, dt, now / 1000);
    this.renderer.render(this.scene, this.camera);
  }

  dispose() {
    cancelAnimationFrame(this.frame);
    this.observer.disconnect();
    this.scene.traverse((thing) => {
      if (thing.geometry) thing.geometry.dispose();
      if (thing.material) for (const m of [].concat(thing.material)) m.dispose();
    });
    this.renderer.dispose();
    this.canvas.remove();
  }
}

function pick(choice, calm) {
  const pool = calm ? CALM : SCENES;
  return pool.find((s) => s.id === choice) || pool[Math.floor(Math.random() * pool.length)];
}

window.joyshareScenes = {
  ids: SCENES.map((s) => s.id),
  // Starts a scene in `container`. choice is a scene id or "random". Returns the stage, or null if 3D isn't available.
  start(container, { choice = "random", calm = false } = {}) {
    try {
      return new Stage(container, pick(choice, calm));
    } catch (err) {
      console.warn("3D scene unavailable:", err);
      container.replaceChildren();
      return null;
    }
  },
  // A small character on its own (a random one), used for the hint next to the pencil button.
  mascot(container) {
    try {
      return new Stage(container, mascots[Math.floor(Math.random() * mascots.length)]);
    } catch (err) {
      console.warn("3D mascot unavailable:", err);
      container.replaceChildren();
      return null;
    }
  },
};
document.dispatchEvent(new CustomEvent("joyshare:scenes-ready"));
