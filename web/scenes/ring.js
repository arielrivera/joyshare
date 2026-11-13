// Ring (calm): a circle slowly draws itself closed as progress grows. Nothing shakes, flashes or races.
// Shown when the device has "Reduce motion" turned on.
export default {
  id: "ring",
  calm: true,
  create({ THREE, scene, colors }) {
    const RADIUS = 2.1, THICK = 0.26;
    const track = new THREE.Mesh(new THREE.TorusGeometry(RADIUS, THICK * 0.55, 12, 80),
      new THREE.MeshBasicMaterial({ color: colors.muted, transparent: true, opacity: 0.3 }));
    const arcMaterial = new THREE.MeshStandardMaterial({ color: colors.hot, roughness: 0.5, side: THREE.DoubleSide });
    const arc = new THREE.Mesh(new THREE.BufferGeometry(), arcMaterial);
    const heart = new THREE.Mesh(new THREE.SphereGeometry(0.75, 24, 16), new THREE.MeshStandardMaterial({ color: colors.third, roughness: 0.5 }));
    scene.add(track, arc, heart);

    let drawn = -1;

    return {
      update(state) {
        // Rebuild the arc only when it has visibly grown, so the change is smooth and unhurried.
        const amount = Math.max(0.002, state.progress);
        if (Math.abs(amount - drawn) > 0.004) {
          drawn = amount;
          arc.geometry.dispose();
          const sweep = Math.PI * 2 * amount;
          arc.geometry = new THREE.TorusGeometry(RADIUS, THICK, 14, 96, sweep);
          arc.rotation.z = Math.PI / 2 - sweep;   // the arc starts at the top and grows clockwise
        }
        const settle = Math.min(1, state.ended);
        if (state.status === "done") {
          arcMaterial.color.lerpColors(colors.hot, colors.zap, settle);
          heart.material.color.lerpColors(colors.third, colors.zap, settle);
        } else if (state.status === "failed") {
          arcMaterial.color.lerpColors(colors.hot, colors.muted, settle);
          heart.material.color.lerpColors(colors.third, colors.muted, settle);
        }
        heart.scale.setScalar(0.6 + 0.4 * state.progress);
      },
    };
  },
};
