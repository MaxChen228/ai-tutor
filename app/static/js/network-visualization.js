// network-visualization.js - 知識點網絡視覺化

class KnowledgeNetworkVisualizer {
    constructor() {
        this.svg = null;
        this.simulation = null;
        this.nodes = [];
        this.links = [];
        this.width = 0;
        this.height = 600;
        this.zoom = null;
        this.selectedNode = null;
        this.colorScale = null;
        
        // 初始化顏色方案
        this.colors = {
            category: d3.scaleOrdinal(d3.schemeCategory10),
            degree: d3.scaleSequential(d3.interpolateBlues),
            cluster: d3.scaleOrdinal(d3.schemeSet3)
        };
    }
    
    initialize() {
        // 設定 SVG 容器
        const container = d3.select('#networkGraph');
        this.width = container.node().getBoundingClientRect().width;
        
        // 清除現有內容
        container.selectAll('*').remove();
        
        // 創建 SVG
        this.svg = container.append('svg')
            .attr('width', this.width)
            .attr('height', this.height);
            
        // 設定縮放
        this.zoom = d3.zoom()
            .scaleExtent([0.1, 10])
            .on('zoom', (event) => {
                this.svg.select('.graph-container').attr('transform', event.transform);
            });
            
        this.svg.call(this.zoom);
        
        // 創建圖表容器
        this.svg.append('g').attr('class', 'graph-container');
        
        // 載入初始資料
        this.loadNetworkData();
    }
    
    async loadNetworkData() {
        try {
            this.showLoading(true);
            
            const limit = document.getElementById('nodeLimit').value;
            const threshold = document.getElementById('similarityThreshold').value;
            
            const response = await fetch(`/admin/api/network-data?limit=${limit}&min_similarity=${threshold}`, {
                headers: {
                    'Authorization': 'Bearer ' + localStorage.getItem('jwt_token')
                }
            });
            
            if (!response.ok) {
                throw new Error('載入資料失敗');
            }
            
            const data = await response.json();
            this.nodes = data.nodes;
            this.links = data.links;
            
            // 計算節點度數
            this.calculateNodeDegrees();
            
            // 更新統計資訊
            this.updateStatistics(data.stats);
            
            // 繪製網絡
            this.renderNetwork();
            
            // 更新圖例
            this.updateLegend();
            
        } catch (error) {
            console.error('載入網絡資料錯誤:', error);
            this.showError('載入網絡資料時發生錯誤');
        } finally {
            this.showLoading(false);
        }
    }
    
    calculateNodeDegrees() {
        // 初始化度數
        this.nodes.forEach(node => {
            node.degree = 0;
            node.connections = [];
        });
        
        // 計算每個節點的連接數
        this.links.forEach(link => {
            const sourceNode = this.nodes.find(n => n.id === link.source);
            const targetNode = this.nodes.find(n => n.id === link.target);
            
            if (sourceNode && targetNode) {
                sourceNode.degree++;
                targetNode.degree++;
                sourceNode.connections.push(targetNode);
                targetNode.connections.push(sourceNode);
            }
        });
    }
    
    renderNetwork() {
        const layoutType = document.getElementById('layoutType').value;
        const colorBy = document.getElementById('colorBy').value;
        
        // 清除現有圖表
        this.svg.select('.graph-container').selectAll('*').remove();
        
        // 設定力模擬
        this.setupSimulation(layoutType);
        
        // 繪製連結
        this.renderLinks();
        
        // 繪製節點
        this.renderNodes(colorBy);
        
        // 繪製標籤
        this.renderLabels();
        
        // 啟動模擬
        this.simulation.restart();
    }
    
    setupSimulation(layoutType) {
        this.simulation = d3.forceSimulation(this.nodes);
        
        switch (layoutType) {
            case 'force':
                this.simulation
                    .force('link', d3.forceLink(this.links)
                        .id(d => d.id)
                        .distance(d => 100 - (d.weight * 50))
                        .strength(d => d.weight))
                    .force('charge', d3.forceManyBody().strength(-300))
                    .force('center', d3.forceCenter(this.width / 2, this.height / 2))
                    .force('collision', d3.forceCollide().radius(25));
                break;
                
            case 'circular':
                this.simulation
                    .force('link', d3.forceLink(this.links)
                        .id(d => d.id)
                        .distance(80)
                        .strength(0.1))
                    .force('charge', d3.forceManyBody().strength(-100))
                    .force('center', d3.forceCenter(this.width / 2, this.height / 2))
                    .force('radial', d3.forceRadial(200, this.width / 2, this.height / 2).strength(0.8));
                break;
                
            case 'tree':
                this.simulation
                    .force('link', d3.forceLink(this.links)
                        .id(d => d.id)
                        .distance(100)
                        .strength(0.8))
                    .force('charge', d3.forceManyBody().strength(-200))
                    .force('center', d3.forceCenter(this.width / 2, this.height / 2))
                    .force('y', d3.forceY().strength(0.1));
                break;
        }
        
        this.simulation.on('tick', () => this.tick());
    }
    
    renderLinks() {
        const container = this.svg.select('.graph-container');
        
        const links = container.selectAll('.link')
            .data(this.links)
            .enter().append('line')
            .attr('class', 'link')
            .style('stroke-width', d => Math.sqrt(d.weight * 5))
            .style('stroke-opacity', d => Math.max(0.2, d.weight));
    }
    
    renderNodes(colorBy) {
        const container = this.svg.select('.graph-container');
        
        // 設定顏色比例
        this.setColorScale(colorBy);
        
        const nodes = container.selectAll('.node')
            .data(this.nodes)
            .enter().append('circle')
            .attr('class', 'node')
            .attr('r', d => Math.max(8, Math.sqrt(d.degree) * 3))
            .style('fill', d => this.getNodeColor(d, colorBy))
            .on('mouseover', (event, d) => this.showTooltip(event, d))
            .on('mouseout', () => this.hideTooltip())
            .on('click', (event, d) => this.selectNode(d))
            .call(d3.drag()
                .on('start', (event, d) => this.dragStarted(event, d))
                .on('drag', (event, d) => this.dragged(event, d))
                .on('end', (event, d) => this.dragEnded(event, d)));
    }
    
    renderLabels() {
        const container = this.svg.select('.graph-container');
        
        const labels = container.selectAll('.node-label')
            .data(this.nodes)
            .enter().append('text')
            .attr('class', 'node-label')
            .text(d => d.label.length > 15 ? d.label.substring(0, 15) + '...' : d.label)
            .style('font-size', d => Math.max(8, Math.sqrt(d.degree) + 8) + 'px');
    }
    
    setColorScale(colorBy) {
        switch (colorBy) {
            case 'category':
                this.colorScale = this.colors.category;
                break;
            case 'degree':
                const maxDegree = d3.max(this.nodes, d => d.degree);
                this.colorScale = this.colors.degree.domain([0, maxDegree]);
                break;
            case 'cluster':
                this.colorScale = this.colors.cluster;
                break;
        }
    }
    
    getNodeColor(node, colorBy) {
        switch (colorBy) {
            case 'category':
                return this.colorScale(node.group);
            case 'degree':
                return this.colorScale(node.degree);
            case 'cluster':
                return this.colorScale(node.cluster || 0);
            default:
                return '#1f77b4';
        }
    }
    
    tick() {
        // 更新連結位置
        this.svg.selectAll('.link')
            .attr('x1', d => d.source.x)
            .attr('y1', d => d.source.y)
            .attr('x2', d => d.target.x)
            .attr('y2', d => d.target.y);
        
        // 更新節點位置
        this.svg.selectAll('.node')
            .attr('cx', d => d.x)
            .attr('cy', d => d.y);
        
        // 更新標籤位置
        this.svg.selectAll('.node-label')
            .attr('x', d => d.x)
            .attr('y', d => d.y + 30);
    }
    
    showTooltip(event, node) {
        const tooltip = d3.select('#tooltip');
        
        tooltip.style('display', 'block')
            .html(`
                <strong>${node.label}</strong><br>
                分類: ${node.group}<br>
                連接數: ${node.degree}<br>
                摘要: ${node.title}
            `)
            .style('left', (event.pageX + 10) + 'px')
            .style('top', (event.pageY - 10) + 'px');
    }
    
    hideTooltip() {
        d3.select('#tooltip').style('display', 'none');
    }
    
    selectNode(node) {
        // 重置所有節點樣式
        this.svg.selectAll('.node').style('stroke', '#fff').style('stroke-width', 2);
        
        // 高亮選中節點
        this.svg.selectAll('.node')
            .filter(d => d.id === node.id)
            .style('stroke', '#ff6b6b')
            .style('stroke-width', 4);
        
        this.selectedNode = node;
        this.showNodeDetails(node);
    }
    
    showNodeDetails(node) {
        const detailsCard = document.getElementById('nodeDetailsCard');
        const detailsContent = document.getElementById('nodeDetails');
        
        detailsContent.innerHTML = `
            <div class="mb-3">
                <strong>ID:</strong> ${node.id}<br>
                <strong>標題:</strong> ${node.label}
            </div>
            <div class="mb-3">
                <strong>分類:</strong> 
                <span class="badge bg-primary">${node.group}</span>
            </div>
            <div class="mb-3">
                <strong>連接數:</strong> ${node.degree}
            </div>
            <div class="mb-3">
                <strong>摘要:</strong><br>
                <small class="text-muted">${node.title}</small>
            </div>
            <div class="d-grid gap-2">
                <button class="btn btn-sm btn-outline-primary" onclick="highlightConnections(${node.id})">
                    顯示關聯
                </button>
                <button class="btn btn-sm btn-outline-info" onclick="centerOnNode(${node.id})">
                    居中顯示
                </button>
            </div>
        `;
        
        detailsCard.style.display = 'block';
    }
    
    updateStatistics(stats) {
        document.getElementById('nodeCount').textContent = stats.node_count;
        document.getElementById('linkCount').textContent = stats.link_count;
        
        if (this.nodes.length > 0) {
            const avgDegree = d3.mean(this.nodes, d => d.degree);
            const maxDegree = d3.max(this.nodes, d => d.degree);
            
            document.getElementById('avgDegree').textContent = avgDegree.toFixed(1);
            document.getElementById('maxDegree').textContent = maxDegree;
        }
    }
    
    updateLegend() {
        const colorBy = document.getElementById('colorBy').value;
        const legendContent = document.getElementById('legendContent');
        
        let legendHTML = '';
        
        switch (colorBy) {
            case 'category':
                const categories = [...new Set(this.nodes.map(n => n.group))];
                categories.forEach(cat => {
                    const color = this.colors.category(cat);
                    legendHTML += `
                        <div class="legend-item">
                            <div class="legend-color" style="background-color: ${color}"></div>
                            <span>${cat}</span>
                        </div>
                    `;
                });
                break;
                
            case 'degree':
                legendHTML = `
                    <div class="legend-item">
                        <div class="legend-color" style="background: linear-gradient(to right, #f7fbff, #08519c)"></div>
                        <span>連接數 (低 → 高)</span>
                    </div>
                `;
                break;
                
            case 'cluster':
                legendHTML = `
                    <div class="legend-item">
                        <span>按聚類著色</span>
                    </div>
                `;
                break;
        }
        
        legendContent.innerHTML = legendHTML;
    }
    
    // 拖拽事件處理
    dragStarted(event, d) {
        if (!event.active) this.simulation.alphaTarget(0.3).restart();
        d.fx = d.x;
        d.fy = d.y;
    }
    
    dragged(event, d) {
        d.fx = event.x;
        d.fy = event.y;
    }
    
    dragEnded(event, d) {
        if (!event.active) this.simulation.alphaTarget(0);
        d.fx = null;
        d.fy = null;
    }
    
    // 縮放控制
    zoomIn() {
        this.svg.transition().call(this.zoom.scaleBy, 1.5);
    }
    
    zoomOut() {
        this.svg.transition().call(this.zoom.scaleBy, 0.67);
    }
    
    resetZoom() {
        this.svg.transition().call(this.zoom.transform, d3.zoomIdentity);
    }
    
    // 搜尋功能
    searchNodes(query) {
        const results = this.nodes.filter(node => 
            node.label.toLowerCase().includes(query.toLowerCase()) ||
            node.title.toLowerCase().includes(query.toLowerCase())
        );
        
        return results.slice(0, 10); // 最多返回10個結果
    }
    
    highlightSearchResults(results) {
        // 重置所有節點
        this.svg.selectAll('.node').style('opacity', 0.3);
        
        // 高亮搜尋結果
        this.svg.selectAll('.node')
            .filter(d => results.some(r => r.id === d.id))
            .style('opacity', 1)
            .style('stroke', '#ff6b6b')
            .style('stroke-width', 3);
    }
    
    clearHighlight() {
        this.svg.selectAll('.node')
            .style('opacity', 1)
            .style('stroke', '#fff')
            .style('stroke-width', 2);
    }
    
    // 顯示載入狀態
    showLoading(show) {
        const spinner = document.getElementById('loadingSpinner');
        const graph = document.getElementById('networkGraph');
        
        if (show) {
            spinner.style.display = 'block';
            graph.style.opacity = '0.5';
        } else {
            spinner.style.display = 'none';
            graph.style.opacity = '1';
        }
    }
    
    showError(message) {
        const container = d3.select('#networkGraph');
        container.selectAll('*').remove();
        container.append('div')
            .attr('class', 'alert alert-danger')
            .style('margin', '20px')
            .text(message);
    }
}

// 全域實例
let networkVisualizer = null;

// 初始化函數
function initializeNetwork() {
    networkVisualizer = new KnowledgeNetworkVisualizer();
    networkVisualizer.initialize();
}

// 更新網絡
function updateNetwork() {
    if (networkVisualizer) {
        networkVisualizer.loadNetworkData();
    }
}

// 縮放控制
function zoomIn() {
    if (networkVisualizer) networkVisualizer.zoomIn();
}

function zoomOut() {
    if (networkVisualizer) networkVisualizer.zoomOut();
}

function resetZoom() {
    if (networkVisualizer) networkVisualizer.resetZoom();
}

// 搜尋節點
function searchNode() {
    const query = document.getElementById('nodeSearch').value.trim();
    const resultsDiv = document.getElementById('searchResults');
    
    if (!query) {
        resultsDiv.innerHTML = '';
        networkVisualizer.clearHighlight();
        return;
    }
    
    const results = networkVisualizer.searchNodes(query);
    
    if (results.length > 0) {
        let html = '<div class="list-group list-group-flush">';
        results.forEach(node => {
            html += `
                <button class="list-group-item list-group-item-action py-2" 
                        onclick="selectSearchResult(${node.id})">
                    <div class="fw-bold">${node.label}</div>
                    <small class="text-muted">${node.title}</small>
                </button>
            `;
        });
        html += '</div>';
        resultsDiv.innerHTML = html;
        
        networkVisualizer.highlightSearchResults(results);
    } else {
        resultsDiv.innerHTML = '<div class="text-muted p-2">找不到匹配的節點</div>';
        networkVisualizer.clearHighlight();
    }
}

// 選中搜尋結果
function selectSearchResult(nodeId) {
    const node = networkVisualizer.nodes.find(n => n.id === nodeId);
    if (node) {
        networkVisualizer.selectNode(node);
        centerOnNode(nodeId);
    }
}

// 居中顯示節點
function centerOnNode(nodeId) {
    const node = networkVisualizer.nodes.find(n => n.id === nodeId);
    if (node && node.x && node.y) {
        const transform = d3.zoomIdentity
            .translate(networkVisualizer.width / 2 - node.x, networkVisualizer.height / 2 - node.y)
            .scale(1.5);
        
        networkVisualizer.svg.transition()
            .duration(750)
            .call(networkVisualizer.zoom.transform, transform);
    }
}

// 高亮連接
function highlightConnections(nodeId) {
    const node = networkVisualizer.nodes.find(n => n.id === nodeId);
    if (!node) return;
    
    // 重置所有元素
    networkVisualizer.svg.selectAll('.node').style('opacity', 0.3);
    networkVisualizer.svg.selectAll('.link').style('opacity', 0.1);
    
    // 高亮選中節點
    networkVisualizer.svg.selectAll('.node')
        .filter(d => d.id === nodeId)
        .style('opacity', 1)
        .style('stroke', '#ff6b6b')
        .style('stroke-width', 4);
    
    // 高亮連接的節點和邊
    const connectedNodeIds = new Set();
    networkVisualizer.links.forEach(link => {
        if (link.source.id === nodeId) {
            connectedNodeIds.add(link.target.id);
        } else if (link.target.id === nodeId) {
            connectedNodeIds.add(link.source.id);
        }
    });
    
    // 高亮連接的節點
    networkVisualizer.svg.selectAll('.node')
        .filter(d => connectedNodeIds.has(d.id))
        .style('opacity', 1)
        .style('stroke', '#4ecdc4')
        .style('stroke-width', 3);
    
    // 高亮相關的邊
    networkVisualizer.svg.selectAll('.link')
        .filter(d => d.source.id === nodeId || d.target.id === nodeId)
        .style('opacity', 0.8)
        .style('stroke', '#ff6b6b')
        .style('stroke-width', 3);
}

// 匯出功能
function exportNetwork() {
    const svgElement = document.querySelector('#networkGraph svg');
    const svgData = new XMLSerializer().serializeToString(svgElement);
    
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const img = new Image();
    
    canvas.width = networkVisualizer.width;
    canvas.height = networkVisualizer.height;
    
    img.onload = function() {
        ctx.drawImage(img, 0, 0);
        
        const link = document.createElement('a');
        link.download = 'knowledge-network.png';
        link.href = canvas.toDataURL();
        link.click();
    };
    
    img.src = 'data:image/svg+xml;base64,' + btoa(unescape(encodeURIComponent(svgData)));
}