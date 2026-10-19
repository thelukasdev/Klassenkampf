'use strict';
importScripts('/demo-engine.js');
onmessage=event=>{const {id,board}=event.data;postMessage({id,column:DemoGame.chooseMove(board)});};
