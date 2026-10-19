// 用无头 Chromium 逐帧渲染 scene.html。
//
//   node render.cjs info   <build>             导出时长、场景起点与配乐提示 -> <build>/cues.json
//   node render.cjs stills <build> t1 t2 ...   导出指定时刻的静帧 -> <build>/still_<t>.png
//   node render.cjs video  <build> [workers]   并行渲染视频分段 -> <build>/chunks-<hash>/*.mp4 + segments.txt
//
// 视频按 10 秒一段渲染，已完成的段会被跳过，中断后重跑可以接着渲染；
// 段目录名带 scene.html 的哈希，画面改动后不会误用旧的分段。
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { spawn, execSync } = require('child_process');

let playwright;
try {
  playwright = require('playwright');
} catch {
  playwright = require(path.join(execSync('npm root -g').toString().trim(), 'playwright'));
}

const FPS = 30;
const W = 1920, H = 1080;
const CHUNK = 300;
const ROOT = __dirname;

async function openScene(browser) {
  const page = await browser.newPage({ viewport: { width: W, height: H }, deviceScaleFactor: 1 });
  // 所有请求都直接从本地目录读取，不经过网络
  await page.route('http://scene.local/**', route => {
    const rel = decodeURIComponent(new URL(route.request().url()).pathname).replace(/^\/+/, '');
    route.fulfill({ path: path.join(ROOT, rel) });
  });
  page.on('pageerror', e => { console.error('page error:', e.message); process.exitCode = 1; });
  await page.goto('http://scene.local/scene.html');
  await page.evaluate(() => window.ready);
  return page;
}

function encoder(out) {
  const ff = spawn('ffmpeg', [
    '-y', '-loglevel', 'error',
    '-f', 'image2pipe', '-framerate', String(FPS), '-c:v', 'png', '-i', '-',
    '-c:v', 'libx264', '-preset', 'medium', '-crf', '18', '-pix_fmt', 'yuv420p', '-g', '60',
    out,
  ], { stdio: ['pipe', 'inherit', 'inherit'] });
  const done = new Promise((res, rej) => ff.on('close', c => (c === 0 ? res() : rej(new Error(`ffmpeg exited ${c}`)))));
  return { ff, done };
}

// 一个工作页不断从队列里取段来渲染。用 CDP 直接截图（无损 PNG、快速压缩），
// 比 page.screenshot 的 PNG 快五倍左右。
async function worker(browser, queue, total, progress) {
  const page = await openScene(browser);
  const cdp = await page.context().newCDPSession(page);
  for (let job; (job = queue.shift());) {
    const part = job.out.replace(/\.mp4$/, '.part.mp4');
    const { ff, done } = encoder(part);
    for (let i = job.from; i < Math.min(total, job.from + CHUNK); i++) {
      await page.evaluate(t => window.render(t), i / FPS);
      const { data } = await cdp.send('Page.captureScreenshot', { format: 'png', optimizeForSpeed: true });
      if (!ff.stdin.write(Buffer.from(data, 'base64'))) await new Promise(r => ff.stdin.once('drain', r));
      progress();
    }
    ff.stdin.end();
    await done;
    fs.renameSync(part, job.out);
  }
  await page.close();
}

async function main() {
  const [mode, build, ...rest] = process.argv.slice(2);
  fs.mkdirSync(build, { recursive: true });
  const browser = await playwright.chromium.launch({ args: ['--font-render-hinting=none'] });
  try {
    if (mode === 'info') {
      const page = await openScene(browser);
      const info = await page.evaluate(() => ({ duration: window.DURATION, sceneStarts: window.SCENE_STARTS, cues: window.CUES }));
      fs.writeFileSync(path.join(build, 'cues.json'), JSON.stringify(info, null, 1));
      console.log(`duration ${info.duration.toFixed(2)}s, ${info.cues.length} cues`);
    } else if (mode === 'stills') {
      const page = await openScene(browser);
      for (const t of rest.map(Number)) {
        await page.evaluate(x => window.render(x), t);
        await page.screenshot({ path: path.join(build, `still_${t.toFixed(2)}.png`) });
      }
    } else if (mode === 'video') {
      const workers = Number(rest[0] || 4);
      const page = await openScene(browser);
      const total = Math.ceil((await page.evaluate(() => window.DURATION)) * FPS);
      await page.close();
      const hash = crypto.createHash('sha1').update(fs.readFileSync(path.join(ROOT, 'scene.html'))).digest('hex').slice(0, 10);
      const dir = path.join(build, `chunks-${hash}`);
      fs.mkdirSync(dir, { recursive: true });
      const segs = [], queue = [];
      for (let from = 0; from < total; from += CHUNK) {
        const out = path.resolve(dir, `${String(from / CHUNK).padStart(3, '0')}.mp4`);
        segs.push(out);
        if (!fs.existsSync(out)) queue.push({ from, out });
      }
      const todo = queue.reduce((n, j) => n + Math.min(CHUNK, total - j.from), 0);
      let doneFrames = 0, last = 0;
      const progress = () => {
        doneFrames++;
        const pct = Math.floor(doneFrames / todo * 10);
        if (pct > last) { last = pct; console.log(`frames ${doneFrames}/${todo}`); }
      };
      await Promise.all(Array.from({ length: Math.min(workers, queue.length) }, () => worker(browser, queue, total, progress)));
      fs.writeFileSync(path.join(build, 'segments.txt'), segs.map(s => `file '${s}'`).join('\n') + '\n');
    } else {
      throw new Error(`unknown mode: ${mode}`);
    }
  } finally {
    await browser.close();
  }
}

main().catch(e => { console.error(e); process.exit(1); });
