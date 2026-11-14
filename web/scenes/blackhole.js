// Black hole: rubble orbits a hungry hole and gets swallowed piece by piece as progress grows, while the hole fattens.
// Done: it collapses into a bright new star. Failed: it burps everything back out.
export default {
  id: "blackhole",
  calm: false,
  create({ THREE, scene, colors }) {
    const mat = (color) => new THREE.MeshStandardMaterial({ color, roughness: 0.5, flatShading: true });
    const COUNT = 70;

    const system = new THREE.Group();
    system.rotation.x = 1.05;            // tilted towards us, like looking at a plate
    scene.add(system);

    const hole = new THREE.Mesh(new THREE.SphereGeometry(1, 24, 16), new THREE.MeshBasicMaterial({ color: 0x050505 }));
    scene.add(hole);
    const rim = new THREE.Mesh(new THREE.TorusGeometry(1.08, 0.07, 8, 48), new THREE.MeshBasicMaterial({ color: colors.third }));
    scene.add(rim);
    const disk = new THREE.Mesh(new THREE.TorusGeometry(2.1, 0.5, 2, 64), new THREE.MeshBasicMaterial({ color: colors.hot, transparent: true, opacity: 0.55 }));
    disk.scale.z = 0.05;
    system.add(disk);
    const disk2 = new THREE.Mesh(new THREE.TorusGeometry(3, 0.35, 2, 64), new THREE.MeshBasicMaterial({ color: colors.zap, transparent: true, opacity: 0.4 }));
    disk2.scale.z = 0.05;
    system.add(disk2);

    const star = new THREE.Mesh(new THREE.OctahedronGeometry(0.9), mat(colors.zap));
    star.visible = false;
    scene.add(star);
    const flash = new THREE.Mesh(new THREE.TorusGeometry(1, 0.06, 6, 48), new THREE.MeshBasicMaterial({ color: colors.ink, transparent: true }));
    flash.visible = false;
    scene.add(flash);

    const rocks = [];
    const shapes = [new THREE.BoxGeometry(0.22, 0.22, 0.22), new THREE.TetrahedronGeometry(0.2), new THREE.OctahedronGeometry(0.16)];
    for (let i = 0; i < COUNT; i++) {
      const rock = new THREE.Mesh(shapes[i % 3], mat([colors.ink, colors.hot, colors.third, colors.zap][i % 4]));
      // the ones swallowed first start closest
      rock.userData = { radius: 1.7 + (i / COUNT) * 3 + Math.random() * 0.3, angle: Math.random() * Math.PI * 2, fall: 0, out: 0 };
      system.add(rock);
      rocks.push(rock);
    }

    return {
      update(state, dt, time) {
        const done = state.status === "done", failed = state.status === "failed";
        const p = state.progress;
        let size = 0.55 + p * 0.95 + Math.sin(time * 5) * 0.02;
        if (done) size *= Math.max(0, 1 - state.ended * 2.4);
        if (failed) size *= 1 + Math.sin(Math.min(state.ended, 0.5) * Math.PI * 2) * 0.35;
        hole.scale.setScalar(Math.max(size, 0.001));
        rim.scale.setScalar(Math.max(size, 0.001));
        rim.rotation.z = time * 1.5;
        disk.rotation.z = time * 1.4;
        disk2.rotation.z = -time * 0.8;
        disk.visible = disk2.visible = !done || state.ended < 0.4;

        rocks.forEach((rock, i) => {
          const d = rock.userData;
          const eaten = p * COUNT > i;
          if (failed) d.out += dt * 7;                         // spat back out
          else if (eaten || done) d.fall = Math.min(1, d.fall + dt * (done ? 4 : 1.6));
          const radius = d.radius * (1 - d.fall) + d.out;
          d.angle += dt * (0.6 + 4 / Math.max(radius, 0.4));   // the closer, the faster
          rock.position.set(Math.cos(d.angle) * radius, Math.sin(d.angle) * radius, 0);
          rock.rotation.x += dt * 3; rock.rotation.y += dt * 2;
          rock.scale.setScalar(Math.max(0.001, 1 - d.fall));
          rock.visible = d.fall < 1 && radius < 9;
        });

        if (done && state.ended > 0.4) {
          const t = state.ended - 0.4;
          star.visible = true;
          star.scale.setScalar(Math.min(1, t * 3) * (1 + Math.sin(time * 8) * 0.08));
          star.rotation.y = time * 3; star.rotation.x = time * 1.3;
          flash.visible = t < 1;
          flash.scale.setScalar(1 + t * 7);
          flash.material.opacity = Math.max(0, 1 - t);
        }
      },
    };
  },
};
