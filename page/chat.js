function Chat(id) {
    this.el = $('#'+id);
}

Chat.prototype.message = function (str) {
    $('<div class="msg">').text(str).appendTo(this.el);
};


function login(username) {
    $.ajax({ url: '/ajax/login',
             data: { 'name': username },
             type: 'POST'
           });
}

function message(msg) {
    $.ajax({ url: '/ajax/post',
             data: { 'message': msg },
             type: 'POST'
           });
}   

(function poll(){
    $.ajax({ url: "/ajax/poll", success: function(data){
        //Update your dashboard gauge
        for (var i in data) {
            chat.message(data[i]);
        }
    }, dataType: "json", complete: poll, timeout: 30000 });
})();


var chat;

$(document).ready(function () {
    chat = new Chat("chat");
});
